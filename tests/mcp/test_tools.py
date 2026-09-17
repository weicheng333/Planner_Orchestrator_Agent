from pathlib import Path

from planner_orchestrator_agent.mcp_server import PlannerTools
from planner_orchestrator_agent.storage import Database, PlannerRepository


def _tools(tmp_path: Path) -> PlannerTools:
    return PlannerTools(PlannerRepository(Database(tmp_path / "state.sqlite3")))


def test_registries_do_not_expose_business_write_tools(tmp_path: Path) -> None:
    response = _tools(tmp_path).read_tool_registry()
    assert response.status == "SUCCESS"
    text = str(response.result)
    assert "business_database_write" in text
    assert "send_email" not in text


def test_validate_and_store_plan(tmp_path: Path, valid_plan_payload: dict) -> None:
    tools = _tools(tmp_path)
    validation = tools.validate_dag(valid_plan_payload)
    stored = tools.write_execution_plan("TASK-PLAN-001", valid_plan_payload, "store", 0)
    replayed = tools.write_execution_plan("TASK-PLAN-001", valid_plan_payload, "store", 0)
    assert validation.status == "SUCCESS"
    assert stored.status == "SUCCESS"
    assert replayed.result is not None and replayed.result["replayed"] is True


def test_invalid_dag_is_not_written(tmp_path: Path, valid_plan_payload: dict) -> None:
    valid_plan_payload["nodes"][0]["dependencies"] = ["verify_result"]
    response = _tools(tmp_path).write_execution_plan("TASK-PLAN-001", valid_plan_payload, "invalid", 0)
    assert response.status == "ERROR"
    assert response.error_code == "DAG_INVALID"
    assert response.receipt_ref is None


def test_approval_request_remains_pending(tmp_path: Path, valid_plan_payload: dict) -> None:
    tools = _tools(tmp_path)
    tools.write_execution_plan("TASK-PLAN-001", valid_plan_payload, "plan", 0)
    response = tools.request_human_approval({
        "task_id": "TASK-PLAN-001", "node_id": "build_artifact",
        "requested_permissions": ["部署"], "reason": "需要执行部署", "impact_if_denied": "计划保持 BLOCKED",
    }, "approval")
    assert response.status == "SUCCESS"
    assert response.result is not None and response.result["approval_status"] == "PENDING"


def test_cost_estimate_uses_relative_units(tmp_path: Path, valid_plan_payload: dict) -> None:
    response = _tools(tmp_path).estimate_cost(valid_plan_payload)
    assert response.status == "SUCCESS"
    assert response.result is not None
    assert response.result["currency"] is None
    assert response.result["method"] == "deterministic_relative_units_v1"
