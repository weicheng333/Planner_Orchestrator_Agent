"""跨 Agent 合同的共用类型。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SCHEMA_VERSION = "1.0.0"

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ItemId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
TaskId = Annotated[str, StringConstraints(pattern=r"^TASK-[A-Z0-9][A-Z0-9_-]{2,63}$")]
TraceId = Annotated[str, StringConstraints(pattern=r"^TRACE-[A-Z0-9][A-Z0-9_-]{2,63}$")]
ImmutableRef = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1024, pattern=r"^[a-z][a-z0-9+.-]*://[^\s]+$"),
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True, use_enum_values=True)


class Budget(ContractModel):
    deadline_ms: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=1)
    max_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class RetryLimits(ContractModel):
    max_agent_hops: int = Field(default=12, ge=1, le=100)
    max_same_agent_retries: int = Field(default=2, ge=0, le=10)
    max_verifier_cycles: int = Field(default=2, ge=0, le=10)
    max_replans: int = Field(default=2, ge=0, le=10)
    max_schema_retries: int = Field(default=1, ge=0, le=3)


class TimestampedModel(ContractModel):
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value


class ErrorDetail(ContractModel):
    code: str
    message: NonEmptyText
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)
