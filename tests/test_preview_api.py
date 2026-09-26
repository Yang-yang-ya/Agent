from copy import deepcopy

from fastapi.testclient import TestClient

from agent_runtime.api.app import app
from agent_runtime.core.planning import PlanValidator


client = TestClient(app)


def test_example_preview_matches_core_validator(sample):
    draft = client.get("/api/plans/example").json()
    catalog = client.get("/api/catalog").json()
    response = client.post("/api/plans/validate", json=draft)

    assert "permissions" not in draft["request"]
    assert catalog["mode"] == "plan_preview"
    assert response.status_code == 200
    assert response.json()["valid"] is True
    expected = PlanValidator().validate(*sample[:3], environment_permissions=sample[3])
    assert response.json()["report"] == expected.to_dict()


def test_preview_rejects_untrusted_permissions_and_locates_cycle():
    draft = client.get("/api/plans/example").json()
    injected = deepcopy(draft)
    injected["request"]["permissions"] = ["repo.write.sandbox"]
    response = client.post("/api/plans/validate", json=injected)
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "SCHEMA_INVALID"

    cyclic = deepcopy(draft)
    cyclic["tasks"][0]["depends_on"] = ["t4_patch_verify"]
    response = client.post("/api/plans/validate", json=cyclic)
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["errors"][0]["code"] == "DAG_CYCLE"
    assert "t1_research" in response.json()["errors"][0]["task_ids"]
