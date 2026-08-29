from pathlib import Path

import pytest

from planner_orchestrator_agent.contracts import ExecutionPlan
from planner_orchestrator_agent.storage import Database, PlannerRepository, StorageError


def test_receipt_failure_rolls_back_plan(tmp_path: Path, valid_plan_payload: dict) -> None:
    repository = PlannerRepository(
        Database(tmp_path / "state.sqlite3"),
        new_id=lambda prefix: (_ for _ in ()).throw(RuntimeError("injected failure")),
    )
    with pytest.raises(StorageError) as error:
        repository.write_plan(ExecutionPlan.model_validate(valid_plan_payload), idempotency_key="failure", expected_plan_version=0)
    assert error.value.code == "INTERNAL_STORAGE_ERROR"
    with pytest.raises(StorageError) as missing:
        repository.read_state("TASK-PLAN-001")
    assert missing.value.code == "TASK_NOT_FOUND"
