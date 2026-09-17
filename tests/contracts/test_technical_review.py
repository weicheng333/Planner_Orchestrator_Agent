"""技术方案合同与 DAG 状态门测试，不替代真实模型的选型分析验收。"""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from planner_orchestrator_agent.contracts import ExecutionPlan
from planner_orchestrator_agent.dag import validate_execution_plan
from planner_orchestrator_agent.mcp_server.tools import PlannerTools
from planner_orchestrator_agent.storage import Database, PlannerRepository


def review(status="AWAITING_CONFIRMATION"):
    decision = {
        "id": "data_store", "dimension": "数据存储", "status": status,
        "options": [
            {"id": "managed", "name": "托管存储", "benefits": ["维护少"],
             "tradeoffs": ["依赖服务商"], "cost_notes": "费用待核查"},
            {"id": "self_hosted", "name": "自管存储", "benefits": ["控制程度高"],
             "tradeoffs": ["维护工作多"], "cost_notes": "费用待核查"},
        ],
        "recommendation_id": "managed", "recommendation_reason": "减少家庭应用首版运维负担",
    }
    if status == "CONFIRMED":
        decision.update(selected_option_id="self_hosted", confirmation_ref="approval://example/choice")
    return {"applicability_reason": "多人共享应用需要明确存储方案", "decisions": [decision]}


def codes(payload):
    return {issue.code for issue in validate_execution_plan(ExecutionPlan.model_validate(payload))}


def test_legacy_and_explicit_no_selection_remain_valid(valid_plan_payload):
    assert not codes(valid_plan_payload)
    valid_plan_payload["technical_review"] = {"applicability_reason": "既定方案内的小修，无新增技术选型", "decisions": []}
    assert not codes(valid_plan_payload)


@pytest.mark.parametrize("status", ["DRAFT", "APPROVAL_REQUIRED"])
def test_pending_review_allows_non_ready_plan(valid_plan_payload, status):
    valid_plan_payload.update(status=status, technical_review=review())
    assert not codes(valid_plan_payload)


def test_unmapped_executor_cannot_bypass_pending_review(valid_plan_payload):
    valid_plan_payload["technical_review"] = review()
    assert "TECHNICAL_REVIEW_PENDING" in codes(valid_plan_payload)


def test_dependent_executor_requires_confirmation(valid_plan_payload):
    valid_plan_payload["technical_review"] = review()
    valid_plan_payload["nodes"][1]["technical_decision_ids"] = ["data_store"]
    assert "TECHNICAL_CONFIRMATION_REQUIRED" in codes(valid_plan_payload)


def test_user_may_confirm_non_recommended_option(valid_plan_payload):
    valid_plan_payload["technical_review"] = review("CONFIRMED")
    valid_plan_payload["nodes"][1]["technical_decision_ids"] = ["data_store"]
    assert not codes(valid_plan_payload)


def test_research_stage_can_be_ready_without_executor(valid_plan_payload):
    valid_plan_payload["technical_review"] = {"applicability_reason": "先研究", "decisions": [
        {"id": "data_store", "dimension": "数据存储", "status": "RESEARCH_REQUIRED", "research_required": True}
    ]}
    valid_plan_payload["nodes"][1]["assigned_capability"] = "workflow"
    valid_plan_payload["nodes"][1]["side_effecting"] = False
    assert not codes(valid_plan_payload)


def test_unknown_decision_reference_rejected(valid_plan_payload):
    valid_plan_payload["nodes"][1]["technical_decision_ids"] = ["not_present"]
    assert "UNKNOWN_TECHNICAL_DECISION" in codes(valid_plan_payload)


@pytest.mark.parametrize("mutation", ["missing_confirmation", "fake_choice", "unknown_recommendation", "duplicate_option", "missing_evidence"])
def test_invalid_decision_rejected(valid_plan_payload, mutation):
    value = review("CONFIRMED")
    decision = value["decisions"][0]
    if mutation == "missing_confirmation":
        del decision["confirmation_ref"]
    elif mutation == "fake_choice":
        decision["status"] = "AWAITING_CONFIRMATION"
    elif mutation == "unknown_recommendation":
        decision["recommendation_id"] = "missing"
    elif mutation == "duplicate_option":
        decision["options"][1] = deepcopy(decision["options"][0])
    else:
        decision["research_required"] = True
    valid_plan_payload["technical_review"] = value
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(valid_plan_payload)


def test_write_tool_rejects_pending_ready_without_persistence(valid_plan_payload, tmp_path):
    tools = PlannerTools(PlannerRepository(Database(tmp_path / "state.sqlite3")))
    valid_plan_payload["technical_review"] = review()
    response = tools.write_execution_plan(valid_plan_payload["task_id"], valid_plan_payload, "pending-review", 0)
    assert response.status == "ERROR"
    assert response.error_code == "DAG_INVALID"
    assert response.receipt_ref is None
    assert tools.read_task_state(valid_plan_payload["task_id"]).status == "ERROR"
