from pathlib import Path

import pytest

from planner_orchestrator_agent.contracts import ExecutionPlan, ProgressEvent
from planner_orchestrator_agent.storage import Database, PlannerRepository, StorageError


@pytest.fixture
def repository(tmp_path: Path) -> PlannerRepository:
    counter = iter(range(1, 50))
    return PlannerRepository(
        Database(tmp_path / "state.sqlite3"),
        now=lambda: "2026-08-29T04:00:00+00:00",
        new_id=lambda prefix: f"{prefix}-{next(counter)}",
    )


def _event(task_id: str, node_id: str | None, event_type: str, status: str) -> ProgressEvent:
    return ProgressEvent.model_validate({
        "task_id": task_id, "node_id": node_id, "event_type": event_type, "status": status,
        "evidence_refs": [], "receipt_refs": [], "details": {}, "occurred_at": "2026-08-29T12:01:00+08:00",
    })


def _usage_event(task_id: str, *, tool_calls: int = 0, tokens: int = 0, cost_units: float = 0) -> ProgressEvent:
    return ProgressEvent.model_validate({
        "task_id": task_id, "node_id": "build_artifact", "event_type": "STARTED", "status": "RUNNING",
        "evidence_refs": [], "receipt_refs": [],
        "actual_usage": {"tool_calls": tool_calls, "tokens": tokens, "cost_units": cost_units},
        "details": {}, "occurred_at": "2026-08-29T12:01:00+08:00",
    })


def test_plan_write_replay_and_read(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    first = repository.write_plan(plan, idempotency_key="plan-v1", expected_plan_version=0)
    second = repository.write_plan(plan, idempotency_key="plan-v1", expected_plan_version=0)
    state = repository.read_state(plan.task_id)
    assert first.resource_ref == "plan://TASK-PLAN-001/v1"
    assert second.replayed is True
    assert state["execution_plan"]["version"] == 1


def test_idempotency_conflict(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="same", expected_plan_version=0)
    changed = plan.model_copy(update={"strategy_reason": "不同 payload"})
    with pytest.raises(StorageError) as error:
        repository.write_plan(changed, idempotency_key="same", expected_plan_version=0)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_progress_and_approval_are_append_only(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="plan", expected_plan_version=0)
    event_receipt = repository.append_event(_event(plan.task_id, "build_artifact", "STARTED", "RUNNING"), idempotency_key="event-1")
    approval = repository.request_approval(plan.task_id, {"requested_permissions": ["部署"], "reason": "需要审批"}, idempotency_key="approval-1")
    state = repository.read_state(plan.task_id)
    assert event_receipt.resource_ref.endswith("/events/1")
    assert approval.resource_ref.startswith("approval://")
    assert state["approval_requests"][0]["status"] == "PENDING"


def test_duplicate_completion_with_new_key_is_rejected(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="plan", expected_plan_version=0)
    completed = _event(plan.task_id, "build_artifact", "SUCCEEDED", "SUCCEEDED")
    repository.append_event(completed, idempotency_key="complete-1")
    with pytest.raises(StorageError) as error:
        repository.append_event(completed, idempotency_key="complete-2")
    assert error.value.code == "DUPLICATE_COMPLETION"


def test_replan_limit_is_enforced(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="plan", expected_plan_version=0)
    event = _event(plan.task_id, None, "REPLAN_REQUESTED", "PENDING")
    repository.append_event(event, idempotency_key="replan-1")
    repository.append_event(event, idempotency_key="replan-2")
    with pytest.raises(StorageError) as error:
        repository.append_event(event, idempotency_key="replan-3")
    assert error.value.code == "REPLAN_LIMIT_REACHED"


def test_plan_versions_are_continuous(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    with pytest.raises(StorageError) as error:
        repository.write_plan(plan, idempotency_key="bad-version", expected_plan_version=2)
    assert error.value.code == "PLAN_VERSION_CONFLICT"


@pytest.mark.parametrize(
    ("budget_field", "usage", "expected_code"),
    [
        ("max_tool_calls", {"tool_calls": 13}, "TOOL_BUDGET_REACHED"),
        ("max_tokens", {"tokens": 15001}, "TOKEN_BUDGET_REACHED"),
        ("max_cost", {"cost_units": 20.1}, "COST_BUDGET_REACHED"),
    ],
)
def test_actual_usage_hard_limits(
    repository: PlannerRepository,
    valid_plan_payload: dict,
    budget_field: str,
    usage: dict,
    expected_code: str,
) -> None:
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key=f"plan-{budget_field}", expected_plan_version=0)
    with pytest.raises(StorageError) as error:
        repository.append_event(_usage_event(plan.task_id, **usage), idempotency_key=f"usage-{budget_field}")
    assert error.value.code == expected_code


def test_deadline_is_a_hard_limit(tmp_path: Path, valid_plan_payload: dict) -> None:
    times = iter(["2026-08-29T04:00:00+00:00", "2026-08-29T04:00:02+00:00"])
    counter = iter(range(1, 20))
    repository = PlannerRepository(
        Database(tmp_path / "deadline.sqlite3"),
        now=lambda: next(times),
        new_id=lambda prefix: f"{prefix}-{next(counter)}",
    )
    valid_plan_payload["budget"]["deadline_ms"] = 1000
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="plan-deadline", expected_plan_version=0)
    with pytest.raises(StorageError) as error:
        repository.append_event(_event(plan.task_id, "build_artifact", "STARTED", "RUNNING"), idempotency_key="late")
    assert error.value.code == "DEADLINE_REACHED"


def test_partial_success_replan_keeps_successful_node_and_changes_affected_node(
    repository: PlannerRepository,
    valid_plan_payload: dict,
) -> None:
    first = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(first, idempotency_key="plan-v1", expected_plan_version=0)
    repository.append_event(
        _event(first.task_id, "build_artifact", "SUCCEEDED", "SUCCEEDED"),
        idempotency_key="build-success",
    )
    valid_plan_payload["version"] = 2
    valid_plan_payload["previous_plan_ref"] = "plan://TASK-PLAN-001/v1"
    valid_plan_payload["nodes"][0]["objective"] = "针对失败原因重新获取可信证据。"
    second = ExecutionPlan.model_validate(valid_plan_payload)
    receipt = repository.write_plan(second, idempotency_key="plan-v2", expected_plan_version=1)
    assert receipt.resource_ref == "plan://TASK-PLAN-001/v2"
    state = repository.read_state(first.task_id)
    assert state["execution_plan"]["nodes"][1]["id"] == "build_artifact"


def test_partial_replan_cannot_mutate_successful_node(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    first = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(first, idempotency_key="plan-v1", expected_plan_version=0)
    repository.append_event(
        _event(first.task_id, "build_artifact", "SUCCEEDED", "SUCCEEDED"),
        idempotency_key="build-success",
    )
    valid_plan_payload["version"] = 2
    valid_plan_payload["previous_plan_ref"] = "plan://TASK-PLAN-001/v1"
    valid_plan_payload["nodes"][1]["objective"] = "悄悄重复已经成功的副作用任务。"
    second = ExecutionPlan.model_validate(valid_plan_payload)
    with pytest.raises(StorageError) as error:
        repository.write_plan(second, idempotency_key="plan-v2-bad", expected_plan_version=1)
    assert error.value.code == "SUCCESSFUL_NODE_MUTATED"


def test_same_agent_retry_limit_is_enforced(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    valid_plan_payload["retry_limits"]["max_same_agent_retries"] = 0
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="plan-retry", expected_plan_version=0)
    repository.append_event(_event(plan.task_id, "build_artifact", "FAILED", "FAILED"), idempotency_key="failed")
    with pytest.raises(StorageError) as error:
        repository.append_event(_event(plan.task_id, "build_artifact", "STARTED", "RUNNING"), idempotency_key="retry")
    assert error.value.code == "RETRY_LIMIT_REACHED"


def test_verifier_cycle_limit_is_enforced(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    valid_plan_payload["retry_limits"]["max_verifier_cycles"] = 1
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="plan-verifier", expected_plan_version=0)
    repository.append_event(_event(plan.task_id, "verify_result", "FAILED", "FAILED"), idempotency_key="verify-failed")
    with pytest.raises(StorageError) as error:
        repository.append_event(_event(plan.task_id, "verify_result", "STARTED", "RUNNING"), idempotency_key="verify-again")
    assert error.value.code == "VERIFIER_CYCLE_LIMIT_REACHED"


def test_agent_hop_limit_is_enforced(repository: PlannerRepository, valid_plan_payload: dict) -> None:
    valid_plan_payload["retry_limits"]["max_agent_hops"] = 1
    plan = ExecutionPlan.model_validate(valid_plan_payload)
    repository.write_plan(plan, idempotency_key="plan-hops", expected_plan_version=0)
    repository.append_event(_event(plan.task_id, "build_artifact", "STARTED", "RUNNING"), idempotency_key="hop-1")
    with pytest.raises(StorageError) as error:
        repository.append_event(_event(plan.task_id, "research_inputs", "STARTED", "RUNNING"), idempotency_key="hop-2")
    assert error.value.code == "AGENT_HOP_LIMIT_REACHED"
