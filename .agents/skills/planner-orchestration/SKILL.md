---
name: planner-orchestration
description: 将已有 TaskSpec 转成最小充分执行 DAG，选择 single model、single agent + tools 或 multi-agent 策略，并安排 Research、Executor、Verifier、权限门、预算、终止与 replan。适用于规划或失败后重规划；不用于原始需求澄清、实际执行、深入取证或独立验收。
---

# Planner Orchestration

把已确认的 `TaskSpec` 转成可校验、可路由、可恢复的 `ExecutionPlan`，但不执行计划节点。

## 工作模式

- 新规划：验证 TaskSpec 后生成 version 1。
- 定向 replan：读取当前 plan/ledger，只替换失败或阻塞子图，保留成功节点 receipt/ref。
- 输入不足：输出给 `intake_spec` 的 typed handoff，不在本角色内重新澄清。
- 详细路由条件见 [references/routing.md](references/routing.md)。

## 工作流

1. 验证 TaskSpec ref、目标、范围、交付物、验收、权限和预算；不要重复询问已有事实。
2. 读取最小 capability/tool registry；只加载当前计划需要的项。
3. 运行 complexity gate：simple 使用 single model；单领域少量工具使用 single agent + tools；多领域、多权限或高风险使用 multi-agent。
4. 生成最小 DAG。每个节点包含 objective、dependencies、assigned capability、tools、input refs、expected output schema、producer/checker、权限、成本、风险和并行组。
5. 将确定性步骤优先建模为 workflow/code，不创建多余 Agent 节点。
6. 调用 `estimate_cost`，确保总量不超过 TaskSpec budget；未知预算保持未知，不虚构额度。
7. 调用 `validate_dag`；只局部修复一次 schema、环、依赖、重复工作、producer/checker 或错误并行问题。
8. 选择最低复杂度但足以满足全部 acceptance criteria 的策略。
9. 获得保存授权后，使用幂等键写入 ExecutionPlan；随后输出最小 typed handoff。
10. 收到失败报告时，按 [references/failure-handling.md](references/failure-handling.md) 决定 local retry、approval、affected-subgraph replan 或 terminal escalation。

## 不变量

- 不按角色数量机械拆任务。
- 不并行有传递数据依赖的节点。
- critical acceptance criterion 必须有 producer 和独立 `verifier` checker。
- 不重复已成功且有 receipt 的副作用节点。
- 不自行扩大 Executor 权限，不把权限请求伪装成已批准。
- Planner 不得调用业务执行工具越界完成任务。
- 所有循环受 `max_agent_hops`、`max_same_agent_retries`、`max_verifier_cycles` 和 `max_replans` 限制。

## 输出

按 [references/contracts.md](references/contracts.md) 输出 `ExecutionPlan + SelectedStrategy + routing decisions + termination/replan conditions`。仅在确定性校验和保存都成功后声明计划已持久化；只有 receipt 能证明写入。
