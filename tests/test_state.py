import json
from datetime import datetime, timezone

import pytest

from agent_runtime.core.schemas import (ResultEnvelope, RunState, RunStatus, TaskStatus)
from agent_runtime.core.state import (TransitionError, commit_verified_success,
                                      transition_run, transition_task)


def one_task_run(task):
    return RunState.model_validate_json(json.dumps({
        "schema_version": 1, "run_id": task.run_id, "status": "CREATED", "plan_version": 1,
        "task_ids": [task.task_id], "completed_task_ids": [],
        "budget_used": {"steps": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_seconds": 0.0},
        "updated_at": "2026-09-23T00:00:00Z",
    }))


def verified_result(task):
    return ResultEnvelope.model_validate_json(json.dumps({
        "schema_version": 1, "run_id": task.run_id, "task_id": task.task_id,
        "agent_id": task.agent_id, "status": "SUCCESS", "summary": "Verified result",
        "data": {}, "artifacts": [], "evidence": ["fixture://login-incident"],
        "verifier": {"status": "PASS", "verifier_id": "fixture_verifier", "checks": ["source"]},
        "error": None, "metrics": {}, "completed_at": "2026-09-23T00:00:01Z",
    }))


def test_ready_requires_successful_dependencies_and_optimistic_version(sample):
    task = sample[1][1]
    with pytest.raises(TransitionError, match="dependencies"):
        transition_task(task, TaskStatus.READY, expected_status=TaskStatus.PENDING,
                        expected_version=0, upstream={"t1_research": TaskStatus.RUNNING})
    ready = transition_task(task, TaskStatus.READY, expected_status=TaskStatus.PENDING,
                            expected_version=0, upstream={"t1_research": TaskStatus.SUCCESS})
    assert ready.status == TaskStatus.READY and ready.state_version == 1
    with pytest.raises(TransitionError, match="stale"):
        transition_task(ready, TaskStatus.QUEUED, expected_status=TaskStatus.READY, expected_version=0)


def test_only_verifier_commit_can_mark_task_success(sample):
    task = sample[1][0].model_copy(update={"status": TaskStatus.VERIFYING, "state_version": 4})
    run = one_task_run(task)
    with pytest.raises(TransitionError):
        transition_task(task, TaskStatus.SUCCESS, expected_status=TaskStatus.VERIFYING, expected_version=4)
    completed_task, updated_run = commit_verified_success(
        task, run, verified_result(task), expected_task_version=4,
        expected_run_version=0, checkpoint_ref="checkpoint://one")
    assert completed_task.status == TaskStatus.SUCCESS
    assert updated_run.completed_task_ids == [task.task_id]
    assert updated_run.last_consistent_checkpoint == "checkpoint://one"
    with pytest.raises(TransitionError):
        commit_verified_success(completed_task, updated_run, verified_result(task),
                                expected_task_version=5, expected_run_version=1,
                                checkpoint_ref="checkpoint://two")


def test_run_terminal_and_acceptance_gate(sample):
    task = sample[1][0]
    run = one_task_run(task)
    now = datetime.now(timezone.utc)
    for status in (RunStatus.PLANNING, RunStatus.RUNNING, RunStatus.VERIFYING):
        run = transition_run(run, status, expected_status=run.status,
                             expected_version=run.state_version, updated_at=now)
    with pytest.raises(TransitionError, match="acceptance"):
        transition_run(run, RunStatus.COMPLETED, expected_status=RunStatus.VERIFYING,
                       expected_version=run.state_version, updated_at=now,
                       final_result_ref="artifact://final", acceptance_passed=True)
    run = run.model_copy(update={"completed_task_ids": [task.task_id]})
    done = transition_run(run, RunStatus.COMPLETED, expected_status=RunStatus.VERIFYING,
                          expected_version=run.state_version, updated_at=now,
                          final_result_ref="artifact://final", acceptance_passed=True)
    with pytest.raises(TransitionError):
        transition_run(done, RunStatus.RUNNING, expected_status=RunStatus.COMPLETED,
                       expected_version=done.state_version, updated_at=now)


def test_attempt_limit(sample):
    task = sample[1][0].model_copy(update={"status": TaskStatus.QUEUED, "attempt": 3})
    with pytest.raises(TransitionError, match="attempt"):
        transition_task(task, TaskStatus.RUNNING, expected_status=TaskStatus.QUEUED,
                        expected_version=0)
