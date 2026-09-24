import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from agent_runtime.core.schemas import AgentManifest, Task, TaskContract


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def sample():
    contract = TaskContract.model_validate_json((EXAMPLES / "contract.json").read_text(encoding="utf-8"))
    tasks = TypeAdapter(list[Task]).validate_json((EXAMPLES / "plan.json").read_text(encoding="utf-8"))
    manifests = TypeAdapter(list[AgentManifest]).validate_json((EXAMPLES / "manifests.json").read_text(encoding="utf-8"))
    environment = frozenset(json.loads((EXAMPLES / "environment.json").read_text(encoding="utf-8"))["permissions"])
    return contract, tasks, manifests, environment
