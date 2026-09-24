from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .core.planning import PlanError, PlanValidator
from .core.schemas import AgentManifest, CORE_SCHEMAS, Task, TaskContract


def export_schemas(directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    names = []
    for model in CORE_SCHEMAS:
        name = f"{model.__name__}.schema.json"
        (directory / name).write_text(json.dumps(model.model_json_schema(), ensure_ascii=False,
                                               indent=2) + "\n", encoding="utf-8")
        names.append(name)
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-framework")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a trusted contract and static Task DAG")
    for name in ("contract", "plan", "manifests", "environment"):
        validate.add_argument(f"--{name}", type=Path, required=True)
    export = sub.add_parser("export-schemas", help="Export seven JSON Schemas")
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "export-schemas":
            result = {"exported": export_schemas(args.output)}
        else:
            contract = TaskContract.model_validate_json(args.contract.read_text(encoding="utf-8"))
            plan = TypeAdapter(list[Task]).validate_json(args.plan.read_text(encoding="utf-8"))
            manifests = TypeAdapter(list[AgentManifest]).validate_json(args.manifests.read_text(encoding="utf-8"))
            environment = json.loads(args.environment.read_text(encoding="utf-8"))
            if not isinstance(environment, dict) or set(environment) != {"permissions"} or not isinstance(environment["permissions"], list):
                raise PlanError("environment policy must contain permissions[]")
            report = PlanValidator().validate(contract, plan, manifests,
                                               environment_permissions=frozenset(environment["permissions"]))
            result = {"valid": True, "run_id": contract.run_id, "plan": report.to_dict()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, ValidationError, PlanError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
