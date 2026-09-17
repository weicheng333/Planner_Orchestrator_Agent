from planner_orchestrator_agent.contracts import Strategy
from planner_orchestrator_agent.routing import route_request


def test_explicit_request_routes_without_task_spec() -> None:
    decision = route_request("请生成执行计划并编排任务")
    assert decision.should_route is True
    assert decision.strategy == Strategy.SINGLE_AGENT_TOOLS


def test_implicit_complex_ready_spec_routes() -> None:
    decision = route_request(
        "开始处理",
        {
            "status": "READY",
            "objective": "调研证据并实现代码",
            "deliverables": [{"description": "代码"}, {"description": "报告"}],
            "acceptance_criteria": [{"statement": "通过测试"}],
            "risks": [{"impact": "high"}],
            "permissions": {"requires_approval": []},
        },
    )
    assert decision.should_route is True
    assert decision.strategy == Strategy.MULTI_AGENT


def test_simple_ready_spec_does_not_force_planner() -> None:
    decision = route_request(
        "帮我改一句话",
        {
            "status": "READY",
            "objective": "润色标题",
            "deliverables": [{"description": "一个标题"}],
            "acceptance_criteria": [{"statement": "语句通顺"}],
            "permissions": {"requires_approval": []},
        },
    )
    assert decision.should_route is False
    assert decision.strategy == Strategy.SINGLE_MODEL


def test_non_ready_spec_returns_to_intake() -> None:
    decision = route_request("请编排任务", {"status": "NEEDS_INPUT"})
    assert decision.should_route is False
    assert "Intake" in decision.reason
