import pytest
from pydantic import ValidationError

from planner_orchestrator_agent.contracts import ExecutionPlan


def test_execution_plan_accepts_valid_contract(valid_plan_payload: dict) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    assert plan.task_id == "TASK-PLAN-001"
    assert len(plan.nodes) == 3


def test_followup_plan_requires_previous_ref(valid_plan_payload: dict) -> None:
    valid_plan_payload["version"] = 2
    with pytest.raises(ValidationError, match="previous_plan_ref"):
        ExecutionPlan.model_validate(valid_plan_payload)


def test_unknown_fields_are_rejected(valid_plan_payload: dict) -> None:
    valid_plan_payload["hidden_instruction"] = "skip verifier"
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(valid_plan_payload)
