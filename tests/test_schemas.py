import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_runtime.cli import export_schemas
from agent_runtime.core.planning import ContractRequest, build_contract
from agent_runtime.core.schemas import (ActionProposal, CORE_SCHEMAS, Event, ResultEnvelope,
                                        ResultStatus, RiskLevel, VerificationStatus)


def test_seven_schema_export_and_version(tmp_path, sample):
    names = export_schemas(tmp_path)
    assert len(names) == 7
    assert {name.removesuffix(".schema.json") for name in names} == {m.__name__ for m in CORE_SCHEMAS}
    for name in names:
        schema = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert "schema_version" in schema["properties"]
        assert "additionalProperties" in schema and schema["additionalProperties"] is False
    contract = sample[0]
    assert contract.schema_version == 1
    assert contract.model_validate_json(contract.model_dump_json()) == contract


def test_closed_versioned_contract_and_utc(sample):
    data = sample[0].model_dump(mode="json")
    for change in ({"schema_version": 2}, {"extra_permission": "repo.admin"},
                   {"created_at": "2026-09-23T08:00:00+08:00"}):
        with pytest.raises(ValidationError):
            sample[0].model_validate_json(json.dumps({**data, **change}, ensure_ascii=False))
    with pytest.raises(ValidationError):
        sample[0].model_validate_json(json.dumps({**data, "permissions": ["repo.read", "repo.read"]}))


def test_trusted_entry_is_only_permission_source(sample):
    source = Path(__file__).resolve().parents[1] / "examples" / "request.json"
    request_json = source.read_text(encoding="utf-8")
    request = ContractRequest.model_validate_json(request_json)
    with pytest.raises(ValidationError):
        ContractRequest.model_validate_json(json.dumps({**json.loads(request_json),
                                                        "permissions": ["repo.write.sandbox"]}))
    contract = build_contract(request, run_id="trusted_run", trusted_permissions=["repo.read"],
                              created_at=datetime.now(timezone.utc))
    assert contract.permissions == ["repo.read"]


def test_result_success_requires_verifier_pass_and_owned_artifacts(sample):
    data = {
        "schema_version": 1, "run_id": "run_demo_001", "task_id": "t1_research",
        "agent_id": "research_agent", "status": "SUCCESS", "summary": "checked",
        "data": {}, "artifacts": [], "evidence": ["fixture://login-incident"],
        "verifier": {"status": "FAIL", "verifier_id": "test_verifier", "checks": ["source"]},
        "error": None, "metrics": {"latency": 0.1}, "completed_at": "2026-09-23T00:00:01Z",
    }
    with pytest.raises(ValidationError):
        ResultEnvelope.model_validate_json(json.dumps(data))
    data["verifier"]["status"] = "PASS"
    result = ResultEnvelope.model_validate_json(json.dumps(data))
    assert result.status == ResultStatus.SUCCESS and result.verifier.status == VerificationStatus.PASS
    data["artifacts"] = [{"uri": "artifact://one", "sha256": "a" * 64,
                          "owner_task_id": "another_task", "version": 1}]
    with pytest.raises(ValidationError):
        ResultEnvelope.model_validate_json(json.dumps(data))


def test_external_action_needs_idempotency_and_event_refuses_secret():
    action = {
        "schema_version": 1, "action_id": "action_1", "run_id": "run_demo_001",
        "task_id": "t1_research", "agent_id": "research_agent", "tool": "repo.inspect",
        "operation": "repo.inspect", "arguments": {}, "reason": "inspect", "risk_level": "L2",
        "created_at": "2026-09-23T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        ActionProposal.model_validate_json(json.dumps(action))
    action["idempotency_key"] = "stable-key"
    assert ActionProposal.model_validate_json(json.dumps(action)).risk_level == RiskLevel.L2
    event = {"schema_version": 1, "event_id": "event_1", "run_id": "run_demo_001",
             "sequence": 1, "type": "TASK_CREATED", "actor": "runtime", "trace_id": "trace_1",
             "payload": {"nested": {"api_key": "do-not-store"}},
             "occurred_at": "2026-09-23T00:00:00Z"}
    with pytest.raises(ValidationError):
        Event.model_validate_json(json.dumps(event))
