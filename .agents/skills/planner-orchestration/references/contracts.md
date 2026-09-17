# 输出合同

仅在生成或校验计划时读取。

## ExecutionPlan

必须包含：`task_id`、`version`、`task_spec_ref`、`selected_strategy`、`nodes`、全局 acceptance criteria、权限边界、预算、retry limits、termination conditions、replan conditions 和时间戳。

每个 node 必须说明 WHO、WHAT、WHY、INPUT、CONSTRAINTS、OUTPUT、DONE WHEN、EVIDENCE 和 FAILURE。

新计划包含 technical_review，说明相关性，并记录 decisions（维度、约束、选项优缺点、成本、证据、推荐、选择与确认引用）。不涉及选型时 decisions 为空并说明原因。旧计划缺省为 null 仅用于历史读取兼容，不代表已完成审查。实施节点用 technical_decision_ids 引用依赖的决定；有未定选型的完整实施计划不得 READY。CONFIRMED 必须有 selected_option_id 和 confirmation_ref；推荐不能当作已批准，引用仍须来自真实用户回复或审批记录。

## Typed handoff

默认只传：`TaskSpec ref + current subtask + relevant evidence/artifact refs + minimal constraints/permissions`。禁止默认复制完整聊天记录、隐藏 scratch state 或无关工具输出。

统一 handoff 字段使用仓库 `contracts/handoff.schema.json`。状态、receipt 和 evidence ref 必须来自真实工具结果。
