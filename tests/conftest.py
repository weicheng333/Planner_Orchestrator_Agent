from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "mcp" / "planner_orchestrator-mcp" / "src"
SCRIPTS = ROOT / "scripts"
for path in (SOURCE, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture
def valid_plan_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "task_id": "TASK-PLAN-001",
        "version": 1,
        "previous_plan_ref": None,
        "task_spec_ref": "taskspec://TASK-PLAN-001/v2",
        "status": "READY",
        "selected_strategy": "MULTI_AGENT",
        "strategy_reason": "任务同时需要证据获取、执行和独立验收。",
        "nodes": [
            {
                "id": "research_inputs",
                "objective": "获取实现所需的可信外部证据。",
                "routing_reason": "外部取证属于 research。",
                "dependencies": [],
                "assigned_capability": "research",
                "tools": ["web_search"],
                "input_refs": ["taskspec://TASK-PLAN-001/v2"],
                "expected_output_schema": "schema://research/evidence/v1",
                "produces_acceptance_criteria": ["criterion_evidence"],
                "checks_acceptance_criteria": [],
                "evidence_requirements": ["来源可追溯"],
                "permissions_required": ["读取公开资料"],
                "estimated_cost": {"estimated_tool_calls": 2, "estimated_tokens": 3000, "estimated_cost_units": 3.0},
                "risk": "medium",
                "parallel_group": "work",
                "side_effecting": False,
                "failure_action": "REPLAN",
            },
            {
                "id": "build_artifact",
                "objective": "根据 TaskSpec 生成目标产物。",
                "routing_reason": "代码与文件写入属于 executor。",
                "dependencies": [],
                "assigned_capability": "executor",
                "tools": ["workspace_write"],
                "input_refs": ["taskspec://TASK-PLAN-001/v2"],
                "expected_output_schema": "schema://executor/artifact/v1",
                "produces_acceptance_criteria": ["criterion_artifact"],
                "checks_acceptance_criteria": [],
                "evidence_requirements": ["构建产物和测试结果"],
                "permissions_required": ["写入工作区"],
                "estimated_cost": {"estimated_tool_calls": 4, "estimated_tokens": 5000, "estimated_cost_units": 5.0},
                "risk": "medium",
                "parallel_group": "work",
                "side_effecting": True,
                "failure_action": "COMPENSATE",
            },
            {
                "id": "verify_result",
                "objective": "独立验证证据和最终产物。",
                "routing_reason": "关键验收必须由 verifier 独立检查。",
                "dependencies": ["research_inputs", "build_artifact"],
                "assigned_capability": "verifier",
                "tools": ["test_runner"],
                "input_refs": ["taskspec://TASK-PLAN-001/v2"],
                "expected_output_schema": "schema://verifier/report/v1",
                "produces_acceptance_criteria": [],
                "checks_acceptance_criteria": ["criterion_evidence", "criterion_artifact"],
                "evidence_requirements": ["独立测试报告"],
                "permissions_required": ["读取工作区"],
                "estimated_cost": {"estimated_tool_calls": 2, "estimated_tokens": 2500, "estimated_cost_units": 2.5},
                "risk": "low",
                "parallel_group": None,
                "side_effecting": False,
                "failure_action": "REPLAN",
            },
        ],
        "acceptance_criteria": [
            {"id": "criterion_evidence", "statement": "证据满足来源要求。", "critical": False},
            {"id": "criterion_artifact", "statement": "产物通过独立验收。", "critical": True},
        ],
        "permissions": {
            "available": ["读取公开资料", "读取工作区", "写入工作区"],
            "requires_approval": [],
            "denied": ["发送邮件"],
        },
        "budget": {"deadline_ms": None, "max_tool_calls": 12, "max_tokens": 15000, "max_cost": 20.0},
        "retry_limits": {"max_agent_hops": 12, "max_same_agent_retries": 2, "max_verifier_cycles": 2, "max_replans": 2, "max_schema_retries": 1},
        "termination_conditions": ["所有验收标准有成功 evidence。", "任一硬预算耗尽时停止。"],
        "replan_conditions": ["节点语义失败达到重试上限。", "Verifier 拒绝关键验收。"],
        "created_at": "2026-08-29T12:00:00+08:00",
    }


@pytest.fixture
def clone():
    return deepcopy
