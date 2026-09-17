# Planner & Orchestrator Agent 仓库规则

## 项目目标

本仓库实现 `planner_orchestrator` Custom Agent、`planner-orchestration` Skill 和确定性的本地 Python MCP。系统只负责把已确认 TaskSpec 转成最小充分 ExecutionPlan、选择策略、路由能力并维护计划/进度账本，不执行产品业务动作。

## 路由

- 已有 TaskSpec，需要拆解、策略选择、能力路由、预算、权限门、终止条件或 replan 时使用本 Agent。
- raw request 或需求不完整时返回 `intake_spec` typed handoff，不自行澄清需求。
- 深入取证交给 `research`，代码或业务动作交给 `executor`，独立验收交给 `verifier`。
- 简单任务返回简化 plan，不为凑齐角色而启动 multi-agent。

## 强制边界

- 不编造用户要求、权限、证据、工具结果、成本或成功状态。
- 不并行有真实数据依赖的节点，不生成环，不重复已成功且有 receipt 的副作用节点。
- 权限不足时只生成审批请求，不自动提权或设计绕过路径。
- 所有 retry、replan、agent hop 和 verifier cycle 都有硬上限。
- 计划写入只追加版本；进度事件只追加；所有写操作必须幂等。
- MCP 不暴露 shell、Git、邮件、支付或任何业务系统写工具。

## 开发规则

- Python 为默认技术栈。
- 每批改动后运行相关测试；必要测试未通过时不得交付。
- 不提交 SQLite、日志、虚拟环境、密钥或真实本机 Codex 配置。
- 常规卸载保留数据；只有显式 `--purge-data` 才能删除本 Agent 数据。
