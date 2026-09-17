"""ExecutionPlan、节点、成本与进度事件合同。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .common import Budget, ContractModel, ImmutableRef, ItemId, NonEmptyText, RetryLimits, SCHEMA_VERSION, ShortText, TaskId
from .technical_review import TechnicalReview


class Strategy(StrEnum):
    SINGLE_MODEL = "SINGLE_MODEL"
    SINGLE_AGENT_TOOLS = "SINGLE_AGENT_TOOLS"
    MULTI_AGENT = "MULTI_AGENT"


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    READY = "READY"
    SUPERSEDED = "SUPERSEDED"


class NodeRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CostEstimate(ContractModel):
    estimated_tool_calls: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    estimated_cost_units: float = Field(ge=0, allow_inf_nan=False)


class ActualUsage(ContractModel):
    """单条进度事件新增的实际用量；由执行方报告，Planner 累计校验。"""

    tool_calls: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    cost_units: float = Field(default=0, ge=0, allow_inf_nan=False)


class AcceptanceCriterion(ContractModel):
    id: ItemId
    statement: NonEmptyText
    critical: bool = False


class PlanNode(ContractModel):
    id: ItemId
    objective: NonEmptyText
    routing_reason: NonEmptyText
    dependencies: list[ItemId] = Field(default_factory=list)
    assigned_capability: Literal["workflow", "research", "executor", "verifier", "human"]
    tools: list[ShortText] = Field(default_factory=list)
    input_refs: list[ImmutableRef] = Field(default_factory=list)
    expected_output_schema: ImmutableRef
    produces_acceptance_criteria: list[ItemId] = Field(default_factory=list)
    checks_acceptance_criteria: list[ItemId] = Field(default_factory=list)
    evidence_requirements: list[NonEmptyText] = Field(default_factory=list)
    permissions_required: list[NonEmptyText] = Field(default_factory=list)
    estimated_cost: CostEstimate
    risk: NodeRisk
    parallel_group: ShortText | None = None
    side_effecting: bool = False
    technical_decision_ids: list[ItemId] = Field(default_factory=list)
    failure_action: Literal["RETRY", "REPLAN", "REQUEST_APPROVAL", "ESCALATE", "COMPENSATE"]


class PermissionBoundary(ContractModel):
    available: list[NonEmptyText] = Field(default_factory=list)
    requires_approval: list[NonEmptyText] = Field(default_factory=list)
    denied: list[NonEmptyText] = Field(default_factory=list)


class ExecutionPlan(ContractModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    task_id: TaskId
    version: int = Field(ge=1)
    previous_plan_ref: ImmutableRef | None = None
    task_spec_ref: ImmutableRef
    status: PlanStatus
    selected_strategy: Strategy
    strategy_reason: NonEmptyText
    nodes: list[PlanNode] = Field(min_length=1, max_length=100)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    permissions: PermissionBoundary = Field(default_factory=PermissionBoundary)
    technical_review: TechnicalReview | None = None
    budget: Budget = Field(default_factory=Budget)
    retry_limits: RetryLimits = Field(default_factory=RetryLimits)
    termination_conditions: list[NonEmptyText] = Field(min_length=1)
    replan_conditions: list[NonEmptyText] = Field(min_length=1)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at 必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_version_link(self) -> "ExecutionPlan":
        if self.version == 1 and self.previous_plan_ref is not None:
            raise ValueError("ExecutionPlan version 1 不得包含 previous_plan_ref")
        if self.version > 1 and self.previous_plan_ref is None:
            raise ValueError("后续 ExecutionPlan 必须包含 previous_plan_ref")
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Plan node id 不得重复")
        criteria = [item.id for item in self.acceptance_criteria]
        if len(criteria) != len(set(criteria)):
            raise ValueError("Acceptance criterion id 不得重复")
        return self


class ProgressEvent(ContractModel):
    task_id: TaskId
    node_id: ItemId | None = None
    event_type: Literal["STARTED", "SUCCEEDED", "FAILED", "BLOCKED", "APPROVAL_REQUESTED", "APPROVED", "REPLAN_REQUESTED", "COMPENSATED"]
    status: Literal["RUNNING", "SUCCEEDED", "FAILED", "BLOCKED", "PENDING"]
    evidence_refs: list[ImmutableRef] = Field(default_factory=list)
    receipt_refs: list[ImmutableRef] = Field(default_factory=list)
    actual_usage: ActualUsage = Field(default_factory=ActualUsage)
    details: dict = Field(default_factory=dict)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_event_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at 必须包含时区")
        return value
