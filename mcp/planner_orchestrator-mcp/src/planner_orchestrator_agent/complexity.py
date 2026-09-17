"""确定性的复杂度门。"""

from __future__ import annotations

from typing import Any

from .contracts import Strategy


def select_strategy(task_spec: dict[str, Any]) -> Strategy:
    deliverables = task_spec.get("deliverables") or []
    criteria = task_spec.get("acceptance_criteria") or []
    risks = task_spec.get("risks") or []
    permissions = task_spec.get("permissions") or {}
    approval_count = len(permissions.get("requires_approval") or [])
    high_risk = any(item.get("impact") in {"high", "critical"} for item in risks if isinstance(item, dict))
    text = " ".join(
        [str(task_spec.get("objective", "")), *[str(item.get("description", "")) for item in deliverables if isinstance(item, dict)]]
    ).casefold()
    needs_research = any(term in text for term in ("research", "搜索", "调研", "证据", "rag"))
    needs_execution = any(term in text for term in ("code", "实现", "部署", "修改", "执行"))

    if len(deliverables) >= 4 or approval_count >= 2 or high_risk or (needs_research and needs_execution):
        return Strategy.MULTI_AGENT
    if len(deliverables) == 1 and len(criteria) <= 2 and approval_count == 0 and not needs_research:
        return Strategy.SINGLE_MODEL
    return Strategy.SINGLE_AGENT_TOOLS
