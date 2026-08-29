import asyncio
from pathlib import Path

from planner_orchestrator_agent.mcp_server import create_server

EXPECTED = {
    "read_capability_registry", "read_tool_registry", "estimate_cost", "validate_dag",
    "read_task_state", "write_execution_plan", "update_progress_ledger", "request_human_approval",
}


def test_server_exposes_exact_allowlist(tmp_path: Path) -> None:
    server = create_server(tmp_path / "state.sqlite3")
    assert {tool.name for tool in asyncio.run(server.list_tools())} == EXPECTED


def test_write_tools_require_idempotency_key(tmp_path: Path) -> None:
    tools = {tool.name: tool for tool in asyncio.run(create_server(tmp_path / "state.sqlite3").list_tools())}
    for name in ("write_execution_plan", "update_progress_ledger", "request_human_approval"):
        assert "idempotency_key" in tools[name].input_schema["required"]
