"""Static DAG validation and trusted contract construction for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from .schemas import (AgentManifest, Budget, Capability, RiskLevel, Task, TaskContract,
                      TaskStatus, utc_time)


class PlanError(ValueError):
    def __init__(self, message: str, *, code: str = "PLAN_INVALID",
                 task_ids: tuple[str, ...] = (), field: str | None = None):
        super().__init__(message)
        self.code = code
        self.task_ids = task_ids
        self.field = field


class ContractRequest(BaseModel):
    """Untrusted intake deliberately has no permissions field."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    goal: str = Field(min_length=1, max_length=4000)
    constraints: list[str]
    acceptance_criteria: list[str] = Field(min_length=1)
    context_refs: list[str]
    budget: Budget


def build_contract(request: ContractRequest, *, run_id: str,
                   trusted_permissions: Iterable[str], created_at: datetime) -> TaskContract:
    return TaskContract(schema_version=1, run_id=run_id, goal=request.goal,
                        constraints=request.constraints, acceptance_criteria=request.acceptance_criteria,
                        permissions=list(trusted_permissions), context_refs=request.context_refs,
                        budget=request.budget, created_at=utc_time(created_at))


@dataclass(frozen=True)
class ToolRule:
    permissions: frozenset[str]
    risk: RiskLevel
    writes_workspace: bool = False


TOOL_RULES = {
    "repo.inspect": ToolRule(frozenset({"repo.read"}), RiskLevel.L0),
    "rag.search.local": ToolRule(frozenset({"rag.search.local"}), RiskLevel.L0),
    "patch.propose": ToolRule(frozenset({"repo.read"}), RiskLevel.L0),
    "sandbox.apply_patch": ToolRule(frozenset({"repo.write.sandbox", "sandbox.execute"}), RiskLevel.L1, True),
    "sandbox.pytest": ToolRule(frozenset({"sandbox.execute"}), RiskLevel.L1),
}

VERIFIER_CRITERIA = frozenset({"root_cause_with_evidence", "pytest_login_passes", "patch_reproducible"})
RISK_ORDER = {RiskLevel.L0: 0, RiskLevel.L1: 1, RiskLevel.L2: 2, RiskLevel.L3: 3}


@dataclass(frozen=True)
class PlanReport:
    task_order: tuple[str, ...]
    parallel_levels: tuple[tuple[str, ...], ...]
    maximum_depth: int
    effective_tools: dict[str, tuple[str, ...]]
    manifest_versions: dict[str, str]

    def to_dict(self) -> dict:
        return {"task_order": list(self.task_order),
                "parallel_levels": [list(level) for level in self.parallel_levels],
                "maximum_depth": self.maximum_depth,
                "effective_tools": {key: list(value) for key, value in self.effective_tools.items()},
                "manifest_versions": self.manifest_versions}


class PlanValidator:
    def validate(self, contract: TaskContract, tasks: list[Task], manifests: list[AgentManifest],
                 *, environment_permissions: frozenset[str]) -> PlanReport:
        if not tasks or len(tasks) > contract.budget.max_tasks or len(tasks) > contract.budget.max_steps:
            raise PlanError("task count exceeds the contract budget", code="TASK_BUDGET_EXCEEDED", field="tasks")
        if len({t.task_id for t in tasks}) != len(tasks):
            raise PlanError("duplicate task_id", code="DUPLICATE_TASK_ID", field="tasks")
        if len({m.agent_id for m in manifests}) != len(manifests):
            raise PlanError("duplicate manifest agent_id", code="DUPLICATE_AGENT_ID")
        if any(t.run_id != contract.run_id for t in tasks):
            raise PlanError("cross-run task", code="CROSS_RUN_TASK")
        if any(t.status != TaskStatus.PENDING or t.attempt != 0 or t.state_version != 0 for t in tasks):
            raise PlanError("new plan tasks must be PENDING at version zero", code="INVALID_INITIAL_STATE")
        if any(t.workspace_ref and t.workspace_ref not in contract.context_refs for t in tasks):
            raise PlanError("task workspace is not a contract context reference", code="WORKSPACE_NOT_IN_CONTEXT")
        if not set(contract.acceptance_criteria) <= VERIFIER_CRITERIA:
            raise PlanError("acceptance criterion has no registered verifier", code="UNKNOWN_ACCEPTANCE_CRITERION",
                            field="request.acceptance_criteria")
        by_id = {t.task_id: t for t in tasks}
        registry = {m.agent_id: m for m in manifests}
        for task in tasks:
            if task.task_id in task.depends_on or not set(task.depends_on) <= set(by_id):
                raise PlanError(f"invalid dependency for {task.task_id}", code="INVALID_DEPENDENCY",
                                task_ids=(task.task_id,), field="depends_on")
            if not task.agent_id or task.agent_id not in registry:
                raise PlanError(f"unregistered agent for {task.task_id}", code="UNREGISTERED_AGENT",
                                task_ids=(task.task_id,), field="agent_id")
        levels: list[tuple[str, ...]] = []
        seen: set[str] = set()
        depth = 0
        while len(seen) < len(tasks):
            ready = [t for t in tasks if t.task_id not in seen and set(t.depends_on) <= seen]
            if not ready:
                raise PlanError("Task DAG contains a cycle", code="DAG_CYCLE",
                                task_ids=tuple(t.task_id for t in tasks if t.task_id not in seen), field="depends_on")
            ready.sort(key=lambda t: (-t.priority, t.created_at, t.task_id))
            level = tuple(t.task_id for t in ready)
            levels.append(level)
            seen.update(level)
            depth += 1
            if depth > contract.budget.max_depth:
                raise PlanError("DAG depth exceeds contract budget", code="DAG_DEPTH_EXCEEDED", field="request.budget.max_depth")
        effective_tools: dict[str, tuple[str, ...]] = {}
        for task in tasks:
            manifest = registry[task.agent_id]
            if task.capability not in manifest.capabilities:
                raise PlanError(f"agent lacks capability for {task.task_id}", code="CAPABILITY_MISMATCH",
                                task_ids=(task.task_id,), field="capability")
            if manifest.timeout_seconds > contract.budget.timeout_seconds or manifest.max_steps > contract.budget.max_steps:
                raise PlanError(f"agent budget exceeds contract for {task.task_id}", code="AGENT_BUDGET_EXCEEDED",
                                task_ids=(task.task_id,), field="request.budget")
            if not task.allowed_tools:
                raise PlanError(f"task has no tools: {task.task_id}", code="NO_TASK_TOOLS",
                                task_ids=(task.task_id,), field="allowed_tools")
            effective = []
            for tool in task.allowed_tools:
                rule = TOOL_RULES.get(tool)
                if rule is None or tool not in manifest.allowed_tools or tool in manifest.forbidden_tools:
                    raise PlanError(f"tool is not registered for {task.task_id}: {tool}", code="TOOL_NOT_ALLOWED",
                                    task_ids=(task.task_id,), field="allowed_tools")
                if not rule.permissions <= set(contract.permissions) & environment_permissions:
                    raise PlanError(f"permission denied for {task.task_id}: {tool}", code="PERMISSION_DENIED",
                                    task_ids=(task.task_id,), field="allowed_tools")
                if RISK_ORDER[rule.risk] > RISK_ORDER[manifest.risk_ceiling] or rule.risk in (RiskLevel.L2, RiskLevel.L3):
                    raise PlanError(f"risk ceiling exceeded for {task.task_id}: {tool}", code="RISK_CEILING_EXCEEDED",
                                    task_ids=(task.task_id,), field="allowed_tools")
                effective.append(tool)
            effective_tools[task.task_id] = tuple(effective)
        def ancestors(task_id: str) -> set[str]:
            result: set[str] = set()
            pending = list(by_id[task_id].depends_on)
            while pending:
                dep = pending.pop()
                if dep not in result:
                    result.add(dep)
                    pending.extend(by_id[dep].depends_on)
            return result
        for i, left in enumerate(tasks):
            for right in tasks[i + 1:]:
                if left.workspace_ref and left.workspace_ref == right.workspace_ref:
                    left_write = any(TOOL_RULES[t].writes_workspace for t in effective_tools[left.task_id])
                    right_write = any(TOOL_RULES[t].writes_workspace for t in effective_tools[right.task_id])
                    if (left_write or right_write) and left.task_id not in ancestors(right.task_id) and right.task_id not in ancestors(left.task_id):
                        raise PlanError(f"parallel workspace conflict: {left.task_id}, {right.task_id}",
                                        code="PARALLEL_WORKSPACE_CONFLICT",
                                        task_ids=(left.task_id, right.task_id), field="workspace_ref")
        order = tuple(task_id for level in levels for task_id in level)
        return PlanReport(order, tuple(levels), depth, effective_tools,
                          {m.agent_id: m.version for m in manifests})
