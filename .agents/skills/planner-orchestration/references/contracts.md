# 输出合同

仅在生成或校验计划时读取。

## ExecutionPlan

必须包含：`task_id`、`version`、`task_spec_ref`、`selected_strategy`、`nodes`、全局 acceptance criteria、权限边界、预算、retry limits、termination conditions、replan conditions 和时间戳。

每个 node 必须说明 WHO、WHAT、WHY、INPUT、CONSTRAINTS、OUTPUT、DONE WHEN、EVIDENCE 和 FAILURE。

## Typed handoff

默认只传：`TaskSpec ref + current subtask + relevant evidence/artifact refs + minimal constraints/permissions`。禁止默认复制完整聊天记录、隐藏 scratch state 或无关工具输出。

统一 handoff 字段使用仓库 `contracts/handoff.schema.json`。状态、receipt 和 evidence ref 必须来自真实工具结果。
