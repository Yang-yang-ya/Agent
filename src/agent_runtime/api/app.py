"""P0 plan preview API and built Web assets. No Agent execution occurs here."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from agent_runtime.core.planning import (
    ContractRequest, PlanError, PlanValidator, TOOL_RULES, VERIFIER_CRITERIA, build_contract,
)
from agent_runtime.core.schemas import AgentManifest, Capability, Identifier, Task, TaskStatus


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = PROJECT_ROOT / "examples"
WEB_DIST = PROJECT_ROOT / "web" / "dist"


class DraftTask(BaseModel):
    """Editable fields only. Runtime identity and status are assigned by the server."""

    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: Identifier
    goal: str = Field(min_length=1, max_length=4000)
    capability: Capability
    depends_on: list[Identifier] = Field(default_factory=list)
    priority: int = Field(default=0, ge=0, le=100)
    agent_id: Identifier
    input_refs: list[str] = Field(default_factory=list)
    allowed_tools: list[Capability] = Field(default_factory=list)
    workspace_ref: str | None = None
    max_attempts: int = Field(default=3, ge=1, le=3)


class PlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    request: ContractRequest
    tasks: list[DraftTask] = Field(min_length=1, max_length=128)


def _read_json(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _manifests() -> list[AgentManifest]:
    return TypeAdapter(list[AgentManifest]).validate_json(
        (EXAMPLES / "manifests.json").read_text(encoding="utf-8"))


def _environment_permissions() -> frozenset[str]:
    return frozenset(_read_json("environment.json")["permissions"])


def _draft_from_example(task: dict) -> dict:
    return {field: task[field] for field in DraftTask.model_fields if field in task}


def _field_path(loc: tuple) -> str:
    return ".".join(str(segment) for segment in loc if segment != "body")


app = FastAPI(title="Agent Plan Workbench", version="0.1.0a1")


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for item in exc.errors():
        errors.append({"code": "SCHEMA_INVALID", "message": item["msg"],
                       "field": _field_path(item["loc"]), "task_ids": []})
    return JSONResponse(status_code=422, content={"valid": False, "errors": errors})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": "plan_preview"}


@app.get("/api/catalog")
def catalog() -> dict:
    return {
        "mode": "plan_preview",
        "agents": [manifest.model_dump(mode="json") for manifest in _manifests()],
        "tools": [{"name": name, "permissions": sorted(rule.permissions),
                   "risk_level": rule.risk.value, "writes_workspace": rule.writes_workspace}
                  for name, rule in TOOL_RULES.items()],
        "acceptance_criteria": sorted(VERIFIER_CRITERIA),
        "preview_permissions": sorted(_environment_permissions()),
    }


@app.get("/api/plans/example")
def example() -> dict:
    return {"request": _read_json("request.json"),
            "tasks": [_draft_from_example(task) for task in _read_json("plan.json")]}


@app.post("/api/plans/validate")
def validate_plan(draft: PlanDraft) -> dict:
    now = datetime.now(timezone.utc)
    permissions = _environment_permissions()
    contract = build_contract(draft.request, run_id="preview", trusted_permissions=permissions,
                              created_at=now)
    tasks = [Task(schema_version=1, task_id=item.task_id, run_id="preview", goal=item.goal,
                  capability=item.capability, depends_on=item.depends_on, status=TaskStatus.PENDING,
                  priority=item.priority, attempt=0, max_attempts=item.max_attempts,
                  agent_id=item.agent_id, input_refs=item.input_refs, output_refs=[],
                  idempotency_scope=item.task_id, created_at=now,
                  allowed_tools=item.allowed_tools, workspace_ref=item.workspace_ref)
             for item in draft.tasks]
    try:
        report = PlanValidator().validate(contract, tasks, _manifests(),
                                          environment_permissions=permissions)
    except PlanError as exc:
        return {"valid": False, "errors": [{"code": exc.code, "message": str(exc),
                                              "field": exc.field, "task_ids": list(exc.task_ids)}]}
    return {"valid": True, "report": report.to_dict(), "errors": []}


if WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/")
def index():
    if not (WEB_DIST / "index.html").is_file():
        return JSONResponse(status_code=404, content={"detail": "Build the Web UI with pnpm build in web/"})
    return FileResponse(WEB_DIST / "index.html")
