"""Pure state transitions. Persistence must commit returned models together later."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from .schemas import (ResultEnvelope, ResultStatus, RunState, RunStatus, Task, TaskStatus,
                      VerificationStatus, utc_time)


class TransitionError(ValueError):
    pass


TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset({TaskStatus.QUEUED, TaskStatus.CANCELLED}),
    TaskStatus.QUEUED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset({TaskStatus.VERIFYING, TaskStatus.RETRY_WAIT,
                                  TaskStatus.WAITING_APPROVAL, TaskStatus.WAITING_REVIEW,
                                  TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.VERIFYING: frozenset({TaskStatus.SUCCESS, TaskStatus.RETRY_WAIT, TaskStatus.FAILED}),
    TaskStatus.RETRY_WAIT: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.WAITING_APPROVAL: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED}),
    TaskStatus.WAITING_REVIEW: frozenset({TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.SUCCESS: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.PLANNING, RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.PLANNING: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.VERIFYING, RunStatus.WAITING_APPROVAL,
                                  RunStatus.WAITING_REVIEW, RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.VERIFYING: frozenset({RunStatus.COMPLETED, RunStatus.RUNNING,
                                    RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.WAITING_APPROVAL: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.WAITING_REVIEW: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


def transition_task(task: Task, target: TaskStatus, *, expected_status: TaskStatus,
                    expected_version: int, upstream: Mapping[str, TaskStatus] | None = None) -> Task:
    if task.status != expected_status or task.state_version != expected_version:
        raise TransitionError("stale task status/version")
    if target not in TASK_TRANSITIONS[task.status]:
        raise TransitionError(f"illegal task transition {task.status} -> {target}")
    if target == TaskStatus.SUCCESS:
        raise TransitionError("SUCCESS requires commit_verified_success")
    if target == TaskStatus.READY:
        if upstream is None or set(upstream) != set(task.depends_on) or any(
                status != TaskStatus.SUCCESS for status in upstream.values()):
            raise TransitionError("all dependencies must be SUCCESS before READY")
    attempt = task.attempt
    if target == TaskStatus.RUNNING and task.status == TaskStatus.QUEUED:
        if attempt >= task.max_attempts:
            raise TransitionError("attempt budget exhausted")
        attempt += 1
    return task.model_copy(update={"status": target, "state_version": task.state_version + 1,
                                   "attempt": attempt})


def commit_verified_success(task: Task, run: RunState, result: ResultEnvelope, *,
                            expected_task_version: int, expected_run_version: int,
                            checkpoint_ref: str) -> tuple[Task, RunState]:
    """One logical commit payload; Phase 2 will persist both with one DB transaction."""
    if task.state_version != expected_task_version or run.state_version != expected_run_version:
        raise TransitionError("stale success commit")
    if task.status not in (TaskStatus.VERIFYING, TaskStatus.WAITING_REVIEW):
        raise TransitionError("task is not ready for verified success")
    if (task.run_id != run.run_id or result.run_id != run.run_id or result.task_id != task.task_id
            or result.agent_id != task.agent_id):
        raise TransitionError("result identity mismatch")
    if result.status != ResultStatus.SUCCESS or result.verifier.status != VerificationStatus.PASS:
        raise TransitionError("Verifier PASS is required")
    if task.task_id not in run.task_ids or task.task_id in run.completed_task_ids:
        raise TransitionError("task is absent or already completed")
    if not checkpoint_ref:
        raise TransitionError("checkpoint reference is required")
    updated_task = task.model_copy(update={"status": TaskStatus.SUCCESS,
                                           "state_version": task.state_version + 1,
                                           "output_refs": list(task.output_refs) + [a.uri for a in result.artifacts]})
    updated_run = run.model_copy(update={"completed_task_ids": [*run.completed_task_ids, task.task_id],
                                         "checkpoint_ref": checkpoint_ref,
                                         "last_consistent_checkpoint": checkpoint_ref,
                                         "state_version": run.state_version + 1})
    return updated_task, updated_run


def transition_run(run: RunState, target: RunStatus, *, expected_status: RunStatus,
                   expected_version: int, updated_at: datetime, final_result_ref: str | None = None,
                   acceptance_passed: bool = False) -> RunState:
    if run.status != expected_status or run.state_version != expected_version:
        raise TransitionError("stale run status/version")
    if target not in RUN_TRANSITIONS[run.status]:
        raise TransitionError(f"illegal run transition {run.status} -> {target}")
    if target == RunStatus.COMPLETED:
        if set(run.task_ids) != set(run.completed_task_ids) or not final_result_ref or not acceptance_passed:
            raise TransitionError("run completion requires all tasks and acceptance checks")
    return run.model_copy(update={"status": target, "state_version": run.state_version + 1,
                                  "updated_at": utc_time(updated_at),
                                  "final_result_ref": final_result_ref or run.final_result_ref})
