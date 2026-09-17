"""导出可交接 JSON Schema。"""

from __future__ import annotations

import json
from pathlib import Path

from .execution_plan import ExecutionPlan
from .handoff import AgentMessage, Handoff


def main() -> int:
    root = Path(__file__).resolve().parents[5]
    output = root / "contracts"
    output.mkdir(parents=True, exist_ok=True)
    schemas = {
        "role-output.schema.json": ExecutionPlan.model_json_schema(),
        "agent-message.schema.json": AgentMessage.model_json_schema(),
        "handoff.schema.json": Handoff.model_json_schema(),
    }
    for name, schema in schemas.items():
        (output / name).write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
