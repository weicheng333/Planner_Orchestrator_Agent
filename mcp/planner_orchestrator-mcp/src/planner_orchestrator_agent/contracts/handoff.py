"""五 Agent 共用 typed handoff。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .common import Budget, ContractModel, ErrorDetail, ImmutableRef, NonEmptyText, SCHEMA_VERSION, TaskId, TraceId

AgentName = Literal["intake_spec", "planner_orchestrator", "research", "executor", "verifier", "human"]


class AgentMessage(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    trace_id: TraceId
    task_id: TaskId
    parent_task_id: TaskId | None = None
    sender: AgentName
    recipient: AgentName
    message_type: Literal["TASK", "RESULT", "EVIDENCE", "REVISION_REQUEST", "APPROVAL_REQUEST", "APPROVAL_RESULT", "ERROR", "STATUS"]
    status: Literal["PENDING", "RUNNING", "BLOCKED", "SUCCEEDED", "FAILED", "ESCALATED"]
    objective: NonEmptyText
    input_refs: list[ImmutableRef] = Field(default_factory=list)
    constraints: list[NonEmptyText] = Field(default_factory=list)
    permissions: list[NonEmptyText] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    acceptance_criteria: list[NonEmptyText] = Field(default_factory=list)
    evidence_refs: list[ImmutableRef] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    error: ErrorDetail | None = None
    next_action: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_error_state(self) -> "AgentMessage":
        if self.status == "FAILED" and self.error is None:
            raise ValueError("FAILED message 必须包含 error")
        if self.error is not None and self.message_type != "ERROR":
            raise ValueError("包含 error 时 message_type 必须为 ERROR")
        return self


class Handoff(AgentMessage):
    message_type: Literal["TASK"] = "TASK"
    plan_ref: ImmutableRef
    node_id: str
    reason_for_delegation: NonEmptyText
    expected_output_schema: ImmutableRef
    artifact_refs: list[ImmutableRef] = Field(default_factory=list)
