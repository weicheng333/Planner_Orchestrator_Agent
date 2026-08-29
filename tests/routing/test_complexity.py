from planner_orchestrator_agent.complexity import select_strategy


def test_simple_task_uses_single_model() -> None:
    task = {"objective": "总结已有文本", "deliverables": [{"description": "摘要"}], "acceptance_criteria": [{"id": "one"}], "permissions": {}, "risks": []}
    assert select_strategy(task) == "SINGLE_MODEL"


def test_single_domain_tools_uses_single_agent() -> None:
    task = {"objective": "用工具处理两个本地文件", "deliverables": [{"description": "文件一"}, {"description": "文件二"}], "acceptance_criteria": [{"id": "one"}], "permissions": {}, "risks": []}
    assert select_strategy(task) == "SINGLE_AGENT_TOOLS"


def test_complex_task_uses_multi_agent() -> None:
    task = {"objective": "先调研证据再实现和部署", "deliverables": [{"description": str(index)} for index in range(4)], "acceptance_criteria": [], "permissions": {"requires_approval": ["deploy"]}, "risks": []}
    assert select_strategy(task) == "MULTI_AGENT"
