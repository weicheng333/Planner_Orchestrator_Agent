# 路由与复杂度门

仅在选择策略或隐式路由边界不清时读取。

## 正向触发

- 已存在可读取的 TaskSpec，需要拆解、依赖、并行、工具、权限或预算规划。
- 需要选择 single model、single agent + tools 或 multi-agent。
- 收到 node failure、revision request 或 verifier rejection，需要 replan。

## 排除

- raw request 或需求实质不完整：交给 `intake_spec`。
- 需要搜索、RAG 或外部证据：交给 `research`。
- 需要写代码、修改文件或业务动作：交给 `executor`。
- 需要独立测试、事实核验或最终验收：交给 `verifier`。
- 普通知识问答或简单摘要：当前 Agent 直接返回无需编排。

## complexity gate

- `SINGLE_MODEL`：单一明确交付物、低风险、无外部工具、无审批。
- `SINGLE_AGENT_TOOLS`：单领域，少量确定性工具，权限边界单一。
- `MULTI_AGENT`：多领域、独立研究与执行、多个权限域、高风险、四个以上交付物，或关键验收需要独立证据链。

边界命中多个等级时选较高等级，但不得只因存在五个角色就选择 multi-agent。
