# planner_orchestrator_mcp

本地 STDIO MCP，为 Planner & Orchestrator Agent 提供确定性的 registry 读取、复杂度成本估算、DAG 校验、版本化计划、进度账本与审批请求。

服务不暴露业务系统写工具，不包含 secret，也不执行计划节点。
