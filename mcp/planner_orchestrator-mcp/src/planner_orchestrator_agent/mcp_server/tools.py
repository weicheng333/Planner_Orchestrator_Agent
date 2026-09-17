"""planner_orchestrator_mcp 的确定性工具实现。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from planner_orchestrator_agent.contracts import ExecutionPlan, ProgressEvent
from planner_orchestrator_agent.contracts.common import NonEmptyText, TaskId
from planner_orchestrator_agent.dag import validate_execution_plan
from planner_orchestrator_agent.registry import CAPABILITY_REGISTRY, TOOL_REGISTRY
from planner_orchestrator_agent.storage import PlannerRepository, StorageError


class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["SUCCESS", "ERROR"]
    error_code: str | None = None
    retryable: bool = False
    receipt_ref: str | None = None
    evidence_ref: str | None = None
    result: dict[str, Any] | None = None
    issues: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_response(self) -> "ToolResponse":
        if self.status == "SUCCESS" and self.error_code is not None:
            raise ValueError("SUCCESS 不得包含 error_code")
        if self.status == "ERROR" and self.error_code is None:
            raise ValueError("ERROR 必须包含 error_code")
        return self


class ApprovalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    task_id: str
    node_id: str | None = None
    requested_permissions: list[NonEmptyText] = Field(min_length=1)
    reason: NonEmptyText
    impact_if_denied: NonEmptyText


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _evidence(kind: str, value: Any) -> str:
    return f"evidence://{kind}/sha256/{hashlib.sha256(_canonical(value).encode()).hexdigest()}"


def _issues(error: ValidationError) -> list[dict[str, Any]]:
    return [{"path": [str(item) for item in issue["loc"]], "message": issue["msg"], "type": issue["type"]} for issue in error.errors(include_input=False, include_url=False)]


def _storage_error(error: StorageError) -> ToolResponse:
    return ToolResponse(
        status="ERROR", error_code=error.code, retryable=error.retryable,
        receipt_ref=error.details.get("receipt_ref"),
        result={"message": error.message, "details": error.details},
    )


class PlannerTools:
    def __init__(self, repository: PlannerRepository) -> None:
        self.repository = repository

    def read_capability_registry(self) -> ToolResponse:
        result = {"capabilities": CAPABILITY_REGISTRY}
        return ToolResponse(status="SUCCESS", evidence_ref=_evidence("capability-registry", result), result=result)

    def read_tool_registry(self) -> ToolResponse:
        result = {"tool_registry": TOOL_REGISTRY}
        return ToolResponse(status="SUCCESS", evidence_ref=_evidence("tool-registry", result), result=result)

    def estimate_cost(self, plan_fragment: dict[str, Any]) -> ToolResponse:
        nodes = plan_fragment.get("nodes")
        if nodes is None:
            nodes = [plan_fragment]
        if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
            return ToolResponse(status="ERROR", error_code="INVALID_PLAN_FRAGMENT", result={"message": "plan_fragment.nodes 必须是对象数组"})
        tool_calls = sum(len(node.get("tools") or []) for node in nodes)
        agent_nodes = sum(node.get("assigned_capability") in {"research", "executor", "verifier"} for node in nodes)
        risk_weight = sum({"low": 0, "medium": 1, "high": 3, "critical": 5}.get(node.get("risk"), 1) for node in nodes)
        estimate = {
            "node_count": len(nodes),
            "estimated_tool_calls": tool_calls,
            "estimated_tokens": len(nodes) * 1200 + agent_nodes * 1800 + risk_weight * 300,
            "estimated_cost_units": round(len(nodes) + tool_calls * 0.25 + agent_nodes * 1.5 + risk_weight * 0.5, 2),
            "currency": None,
            "method": "deterministic_relative_units_v1",
        }
        return ToolResponse(status="SUCCESS", evidence_ref=_evidence("cost-estimate", estimate), result=estimate)

    def validate_dag(self, plan: dict[str, Any]) -> ToolResponse:
        try:
            parsed = ExecutionPlan.model_validate(plan)
        except ValidationError as error:
            return ToolResponse(status="ERROR", error_code="EXECUTION_PLAN_INVALID", issues=_issues(error))
        issues = [issue.as_dict() for issue in validate_execution_plan(parsed)]
        if issues:
            return ToolResponse(status="ERROR", error_code="DAG_INVALID", issues=issues)
        result = {
            "valid": True, "task_id": parsed.task_id, "version": parsed.version,
            "node_count": len(parsed.nodes), "selected_strategy": parsed.selected_strategy,
        }
        return ToolResponse(status="SUCCESS", evidence_ref=_evidence("dag-validation", parsed.model_dump(mode="json")), result=result)

    def read_task_state(self, task_id: str) -> ToolResponse:
        try:
            TypeAdapter(TaskId).validate_python(task_id)
        except ValidationError as error:
            return ToolResponse(status="ERROR", error_code="INVALID_TASK_ID", issues=_issues(error))
        try:
            state = self.repository.read_state(task_id)
        except StorageError as error:
            return _storage_error(error)
        return ToolResponse(status="SUCCESS", evidence_ref=_evidence("task-state", state), result=state)

    def write_execution_plan(self, task_id: str, plan: dict[str, Any], idempotency_key: str, expected_plan_version: int) -> ToolResponse:
        try:
            parsed = ExecutionPlan.model_validate(plan)
        except ValidationError as error:
            return ToolResponse(status="ERROR", error_code="EXECUTION_PLAN_INVALID", issues=_issues(error))
        if parsed.task_id != task_id:
            return ToolResponse(status="ERROR", error_code="TASK_ID_MISMATCH", result={"message": "工具 task_id 与 plan.task_id 不一致"})
        dag_issues = [issue.as_dict() for issue in validate_execution_plan(parsed)]
        if dag_issues:
            return ToolResponse(status="ERROR", error_code="DAG_INVALID", issues=dag_issues)
        try:
            receipt = self.repository.write_plan(parsed, idempotency_key=idempotency_key, expected_plan_version=expected_plan_version)
        except StorageError as error:
            return _storage_error(error)
        return ToolResponse(status="SUCCESS", receipt_ref=receipt.receipt_ref, result={**receipt.as_dict(), "replayed": receipt.replayed})

    def update_progress_ledger(self, task_id: str, event: dict[str, Any], idempotency_key: str) -> ToolResponse:
        try:
            parsed = ProgressEvent.model_validate(event)
        except ValidationError as error:
            return ToolResponse(status="ERROR", error_code="PROGRESS_EVENT_INVALID", issues=_issues(error))
        if parsed.task_id != task_id:
            return ToolResponse(status="ERROR", error_code="TASK_ID_MISMATCH", result={"message": "工具 task_id 与 event.task_id 不一致"})
        try:
            receipt = self.repository.append_event(parsed, idempotency_key=idempotency_key)
        except StorageError as error:
            return _storage_error(error)
        return ToolResponse(status="SUCCESS", receipt_ref=receipt.receipt_ref, result={**receipt.as_dict(), "replayed": receipt.replayed})

    def request_human_approval(self, payload: dict[str, Any], idempotency_key: str) -> ToolResponse:
        try:
            parsed = ApprovalPayload.model_validate(payload)
            TypeAdapter(TaskId).validate_python(parsed.task_id)
        except ValidationError as error:
            return ToolResponse(status="ERROR", error_code="APPROVAL_PAYLOAD_INVALID", issues=_issues(error))
        try:
            receipt = self.repository.request_approval(parsed.task_id, parsed.model_dump(mode="json"), idempotency_key=idempotency_key)
        except StorageError as error:
            return _storage_error(error)
        return ToolResponse(status="SUCCESS", receipt_ref=receipt.receipt_ref, result={**receipt.as_dict(), "replayed": receipt.replayed, "approval_status": "PENDING"})
