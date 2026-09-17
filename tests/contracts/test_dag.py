from planner_orchestrator_agent.contracts import ExecutionPlan
from planner_orchestrator_agent.dag import validate_execution_plan


def _codes(payload: dict) -> set[str]:
    return {issue.code for issue in validate_execution_plan(ExecutionPlan.model_validate(payload))}


def test_valid_dag_has_no_issues(valid_plan_payload: dict) -> None:
    assert _codes(valid_plan_payload) == set()


def test_cycle_is_rejected(valid_plan_payload: dict) -> None:
    valid_plan_payload["nodes"][0]["dependencies"] = ["verify_result"]
    assert "DAG_CYCLE" in _codes(valid_plan_payload)


def test_dependent_nodes_cannot_share_parallel_group(valid_plan_payload: dict) -> None:
    valid_plan_payload["nodes"][2]["parallel_group"] = "work"
    assert "INVALID_PARALLEL_DEPENDENCY" in _codes(valid_plan_payload)


def test_critical_criterion_requires_verifier(valid_plan_payload: dict) -> None:
    valid_plan_payload["nodes"][2]["assigned_capability"] = "workflow"
    assert "MISSING_INDEPENDENT_VERIFIER" in _codes(valid_plan_payload)


def test_duplicate_work_is_rejected(valid_plan_payload: dict) -> None:
    duplicate = dict(valid_plan_payload["nodes"][0])
    duplicate["id"] = "research_duplicate"
    valid_plan_payload["nodes"].append(duplicate)
    assert "DUPLICATE_WORK" in _codes(valid_plan_payload)


def test_denied_permission_is_rejected(valid_plan_payload: dict) -> None:
    valid_plan_payload["nodes"][1]["permissions_required"] = ["发送邮件"]
    assert "PERMISSION_DENIED" in _codes(valid_plan_payload)


def test_budget_is_enforced(valid_plan_payload: dict) -> None:
    valid_plan_payload["budget"]["max_tool_calls"] = 1
    assert "TOOL_BUDGET_EXCEEDED" in _codes(valid_plan_payload)
