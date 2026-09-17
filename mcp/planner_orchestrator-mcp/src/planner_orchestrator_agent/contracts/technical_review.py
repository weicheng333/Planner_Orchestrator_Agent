"""技术选型比较与确认合同；确认引用由调用方提供，不代表服务端已核验用户身份。"""

from typing import Literal

from pydantic import Field, model_validator

from .common import ContractModel, ImmutableRef, ItemId, NonEmptyText


class TechnicalOption(ContractModel):
    id: ItemId
    name: NonEmptyText
    benefits: list[NonEmptyText] = Field(min_length=1)
    tradeoffs: list[NonEmptyText] = Field(min_length=1)
    cost_notes: NonEmptyText
    evidence_refs: list[ImmutableRef] = Field(default_factory=list)


class TechnicalDecision(ContractModel):
    id: ItemId
    dimension: NonEmptyText
    status: Literal["RESEARCH_REQUIRED", "AWAITING_CONFIRMATION", "CONFIRMED"]
    constraints: list[NonEmptyText] = Field(default_factory=list)
    options: list[TechnicalOption] = Field(default_factory=list, max_length=3)
    recommendation_id: ItemId | None = None
    recommendation_reason: NonEmptyText | None = None
    selected_option_id: ItemId | None = None
    confirmation_ref: ImmutableRef | None = None
    research_required: bool = False

    @model_validator(mode="after")
    def validate_decision(self) -> "TechnicalDecision":
        ids = [option.id for option in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("技术选项 id 不得重复")
        for identifier in (self.recommendation_id, self.selected_option_id):
            if identifier is not None and identifier not in ids:
                raise ValueError("推荐或选择必须引用已有技术选项")
        if self.status == "RESEARCH_REQUIRED":
            if not self.research_required:
                raise ValueError("待研究决定必须标记 research_required")
        else:
            if not self.options or self.recommendation_id is None or self.recommendation_reason is None:
                raise ValueError("比较结果必须包含选项、推荐及理由")
            if self.research_required and any(not option.evidence_refs for option in self.options):
                raise ValueError("需要研究的比较必须提供每个选项的证据引用")
            if len(self.options) == 1 and not self.constraints:
                raise ValueError("只有一个可行方案时必须说明约束，不凑选项")
        if self.status == "CONFIRMED":
            if self.selected_option_id is None or self.confirmation_ref is None:
                raise ValueError("已确认选型必须包含选择及确认引用")
        elif self.selected_option_id is not None or self.confirmation_ref is not None:
            raise ValueError("推荐或待确认不能伪装为用户已选择")
        return self


class TechnicalReview(ContractModel):
    applicability_reason: NonEmptyText
    decisions: list[TechnicalDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_decisions(self) -> "TechnicalReview":
        ids = [item.id for item in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("技术决定 id 不得重复")
        return self
