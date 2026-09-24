"""Seven versioned, closed top-level contracts from the execution blueprint."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
Capability = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]{0,79}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SchemaVersion = Literal[1]


def utc_time(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("expected ISO 8601 UTC time") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def unique(items: list[str], label: str) -> list[str]:
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {label}")
    return items


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    RETRY_WAIT = "RETRY_WAIT"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_REVIEW = "WAITING_REVIEW"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunStatus(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_REVIEW = "WAITING_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RiskLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class ResultStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"


class Budget(ClosedModel):
    max_steps: int = Field(ge=1, le=1000)
    max_llm_calls: int = Field(ge=0, le=1000)
    max_tool_calls: int = Field(ge=0, le=10000)
    timeout_seconds: int = Field(ge=1, le=86400)
    max_tasks: int = Field(default=16, ge=1, le=128)
    max_depth: int = Field(default=8, ge=1, le=32)
    max_concurrency: int = Field(default=4, ge=1, le=32)


class BudgetUsed(ClosedModel):
    steps: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)


class TaskContract(ClosedModel):
    schema_version: SchemaVersion
    run_id: Identifier
    goal: str = Field(min_length=1, max_length=4000)
    constraints: list[str]
    acceptance_criteria: list[str] = Field(min_length=1)
    permissions: list[Capability] = Field(min_length=1)
    context_refs: list[str]
    budget: Budget
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_time(cls, value: Any) -> datetime:
        return utc_time(value)

    @field_validator("permissions", "context_refs", "acceptance_criteria")
    @classmethod
    def validate_unique(cls, value: list[str]) -> list[str]:
        return unique(value, "contract entry")


class Task(ClosedModel):
    schema_version: SchemaVersion
    task_id: Identifier
    run_id: Identifier
    goal: str = Field(min_length=1, max_length=4000)
    capability: Capability
    depends_on: list[Identifier]
    status: TaskStatus
    priority: int = Field(ge=0, le=100)
    attempt: int = Field(ge=0)
    max_attempts: int = Field(ge=1, le=3)
    agent_id: Identifier | None = None
    input_refs: list[str]
    output_refs: list[str]
    idempotency_scope: Identifier
    created_at: datetime
    allowed_tools: list[Capability] = Field(default_factory=list)
    workspace_ref: str | None = None
    state_version: int = Field(default=0, ge=0)

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_time(cls, value: Any) -> datetime:
        return utc_time(value)

    @field_validator("depends_on", "allowed_tools")
    @classmethod
    def validate_unique(cls, value: list[str]) -> list[str]:
        return unique(value, "task entry")

    @model_validator(mode="after")
    def check_attempt(self):
        if self.attempt > self.max_attempts:
            raise ValueError("attempt exceeds max_attempts")
        return self


class AgentManifest(ClosedModel):
    schema_version: SchemaVersion
    agent_id: Identifier
    version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
    capabilities: list[Capability] = Field(min_length=1)
    allowed_tools: list[Capability]
    forbidden_tools: list[Capability]
    model_profile: str = Field(min_length=1, max_length=120)
    risk_ceiling: RiskLevel
    timeout_seconds: int = Field(ge=1, le=86400)
    max_steps: int = Field(ge=1, le=1000)

    @model_validator(mode="after")
    def check_tools(self):
        unique(self.capabilities, "manifest capability")
        unique(self.allowed_tools, "manifest tool")
        unique(self.forbidden_tools, "forbidden tool")
        if set(self.allowed_tools) & set(self.forbidden_tools):
            raise ValueError("tool cannot be both allowed and forbidden")
        return self


class RunState(ClosedModel):
    schema_version: SchemaVersion
    run_id: Identifier
    status: RunStatus
    plan_version: int = Field(ge=1)
    task_ids: list[Identifier]
    completed_task_ids: list[Identifier]
    budget_used: BudgetUsed
    checkpoint_ref: str | None = None
    final_result_ref: str | None = None
    updated_at: datetime
    last_consistent_checkpoint: str | None = None
    state_version: int = Field(default=0, ge=0)

    @field_validator("updated_at", mode="before")
    @classmethod
    def validate_time(cls, value: Any) -> datetime:
        return utc_time(value)

    @model_validator(mode="after")
    def check_completed(self):
        unique(self.task_ids, "task id")
        unique(self.completed_task_ids, "completed task id")
        if not set(self.completed_task_ids) <= set(self.task_ids):
            raise ValueError("completed task is not in run")
        if self.status == RunStatus.COMPLETED and (
                set(self.task_ids) != set(self.completed_task_ids) or not self.final_result_ref):
            raise ValueError("COMPLETED requires all tasks and a final result")
        return self


class ActionProposal(ClosedModel):
    schema_version: SchemaVersion
    action_id: Identifier
    run_id: Identifier
    task_id: Identifier
    agent_id: Identifier
    tool: Capability
    operation: Capability
    arguments: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)
    risk_level: RiskLevel
    idempotency_key: str | None = None
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_time(cls, value: Any) -> datetime:
        return utc_time(value)

    @model_validator(mode="after")
    def check_arguments(self):
        try:
            encoded = json.dumps(self.arguments, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("arguments must be finite JSON") from exc
        if len(encoded.encode("utf-8")) > 65536:
            raise ValueError("arguments exceed 64 KiB")
        if self.risk_level in (RiskLevel.L2, RiskLevel.L3) and not self.idempotency_key:
            raise ValueError("external/high-impact action needs an idempotency key")
        return self


class ArtifactRef(ClosedModel):
    uri: str = Field(pattern=r"^artifact://[A-Za-z0-9/_-]+$", max_length=300)
    sha256: Digest
    owner_task_id: Identifier
    version: int = Field(ge=1)


class VerifierRecord(ClosedModel):
    status: VerificationStatus
    verifier_id: Identifier
    checks: list[str]


class ResultEnvelope(ClosedModel):
    schema_version: SchemaVersion
    run_id: Identifier
    task_id: Identifier
    agent_id: Identifier
    status: ResultStatus
    summary: str = Field(min_length=1, max_length=4000)
    data: dict[str, Any]
    artifacts: list[ArtifactRef]
    evidence: list[str]
    verifier: VerifierRecord
    error: str | None = None
    metrics: dict[str, float]
    completed_at: datetime

    @field_validator("completed_at", mode="before")
    @classmethod
    def validate_time(cls, value: Any) -> datetime:
        return utc_time(value)

    @model_validator(mode="after")
    def check_verification(self):
        if self.status == ResultStatus.SUCCESS and self.verifier.status != VerificationStatus.PASS:
            raise ValueError("SUCCESS requires Verifier PASS")
        if self.status != ResultStatus.SUCCESS and self.verifier.status == VerificationStatus.PASS:
            raise ValueError("Verifier PASS requires SUCCESS")
        for artifact in self.artifacts:
            if artifact.owner_task_id != self.task_id:
                raise ValueError("artifact owner differs from task")
        try:
            json.dumps(self.data, allow_nan=False)
            json.dumps(self.metrics, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("result data and metrics must be finite JSON") from exc
        return self


class Event(ClosedModel):
    schema_version: SchemaVersion
    event_id: Identifier
    run_id: Identifier
    task_id: Identifier | None = None
    sequence: int = Field(ge=1)
    type: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,79}$")]
    actor: Identifier
    trace_id: Identifier
    payload: dict[str, Any]
    occurred_at: datetime

    @field_validator("occurred_at", mode="before")
    @classmethod
    def validate_time(cls, value: Any) -> datetime:
        return utc_time(value)

    @model_validator(mode="after")
    def check_payload(self):
        def inspect(value: Any):
            if isinstance(value, dict):
                for key, entry in value.items():
                    if not isinstance(key, str) or any(term in key.casefold() for term in ("secret", "password", "token", "api_key")):
                        raise ValueError("event payload contains a sensitive key")
                    inspect(entry)
            elif isinstance(value, list):
                for entry in value:
                    inspect(entry)
        inspect(self.payload)
        try:
            encoded = json.dumps(self.payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("event payload must be finite JSON") from exc
        if len(encoded.encode("utf-8")) > 8192:
            raise ValueError("event payload exceeds 8 KiB")
        return self


CORE_SCHEMAS = (TaskContract, Task, AgentManifest, RunState, ActionProposal, ResultEnvelope, Event)
