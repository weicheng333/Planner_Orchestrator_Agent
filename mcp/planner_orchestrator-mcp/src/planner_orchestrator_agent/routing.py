"""Planner 路由入口；将触发条件与复杂度策略分开。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .complexity import select_strategy
from .contracts import Strategy


@dataclass(frozen=True)
class RoutingDecision:
    should_route: bool
    strategy: Strategy
    reason: str


_EXPLICIT_TERMS = (
    "planner_orchestrator",
    "planner orchestrator",
    "编排任务",
    "执行计划",
    "任务编排",
    "拆成执行图",
)


def route_request(user_request: str, task_spec: dict[str, Any] | None = None) -> RoutingDecision:
    """判断是否进入 Planner，并在进入时选择最小充分执行策略。"""
    normalized = user_request.casefold().strip()
    explicit = any(term in normalized for term in _EXPLICIT_TERMS)
    if task_spec is None:
        if explicit:
            return RoutingDecision(True, Strategy.SINGLE_AGENT_TOOLS, "用户明确请求规划或编排。")
        return RoutingDecision(False, Strategy.SINGLE_MODEL, "没有 TaskSpec，且未显式请求规划或编排。")

    status = str(task_spec.get("status", "")).upper()
    if status and status != "READY":
        return RoutingDecision(False, Strategy.SINGLE_MODEL, "TaskSpec 尚未 READY，应返回 Intake & Spec。")
    strategy = select_strategy(task_spec)
    if explicit:
        return RoutingDecision(True, strategy, "用户明确请求规划或编排。")
    if strategy == Strategy.SINGLE_MODEL:
        return RoutingDecision(False, strategy, "任务简单，不需要 Planner 介入。")
    return RoutingDecision(True, strategy, "TaskSpec 的复杂度、工具或风险需要确定性规划。")
