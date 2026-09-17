"""本地 STDIO MCP server。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from planner_orchestrator_agent.storage import Database, PlannerRepository

from .tools import PlannerTools, ToolResponse

SERVER_INSTRUCTIONS = """
只提供 Planner & Orchestrator Agent 的 registry 读取、相对成本估算、DAG 校验、版本化计划、进度 ledger 和审批请求。
未注册能力默认拒绝；不提供 shell、Git、邮件、支付或业务数据库工具。审批请求只创建 PENDING 记录，不代表已经批准。
""".strip()


def create_server(database_path: Path | str | None = None) -> MCPServer:
    tools = PlannerTools(PlannerRepository(Database(database_path)))
    server = MCPServer("planner_orchestrator_mcp", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def read_capability_registry() -> ToolResponse:
        """读取五 Agent 与 workflow 的最小 capability registry。"""
        return tools.read_capability_registry()

    @server.tool()
    def read_tool_registry() -> ToolResponse:
        """读取 Planner 可使用的最小工具 allowlist，不返回 secret。"""
        return tools.read_tool_registry()

    @server.tool()
    def estimate_cost(plan_fragment: dict[str, Any]) -> ToolResponse:
        """使用相对单位确定性估算节点、工具调用和 token，不虚构货币价格。"""
        return tools.estimate_cost(plan_fragment)

    @server.tool()
    def validate_dag(plan: dict[str, Any]) -> ToolResponse:
        """校验合同、环、依赖、并行、重复工作、producer/checker、权限和预算。"""
        return tools.validate_dag(plan)

    @server.tool()
    def read_task_state(task_id: str) -> ToolResponse:
        """读取最新 ExecutionPlan、progress ledger 和审批请求。"""
        return tools.read_task_state(task_id)

    @server.tool()
    def write_execution_plan(task_id: str, plan: dict[str, Any], idempotency_key: str, expected_plan_version: int) -> ToolResponse:
        """在服务端校验后以追加版本方式保存 ExecutionPlan。"""
        return tools.write_execution_plan(task_id, plan, idempotency_key, expected_plan_version)

    @server.tool()
    def update_progress_ledger(task_id: str, event: dict[str, Any], idempotency_key: str) -> ToolResponse:
        """向任务 ledger 幂等追加一个 typed progress event。"""
        return tools.update_progress_ledger(task_id, event, idempotency_key)

    @server.tool()
    def request_human_approval(payload: dict[str, Any], idempotency_key: str) -> ToolResponse:
        """创建 PENDING 审批请求；不自动批准或提权。"""
        return tools.request_human_approval(payload, idempotency_key)

    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
