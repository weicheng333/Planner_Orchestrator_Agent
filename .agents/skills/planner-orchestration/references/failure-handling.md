# 失败、重规划与回退

仅在节点失败、权限不足、重复回调、replan 或 rollback 时读取。

- timeout、429、临时 5xx：工具层指数退避和抖动，总计不超过三次；不重跑完整计划。
- tool schema error：只修参数，最多一次。
- 同一 node 语义失败达到 `max_same_agent_retries`：停止局部重试，只 replan 受影响子图。
- 权限不足：创建 approval request，禁止自动提权或设计绕过路径。
- 已成功且有 receipt/ref 的节点在 replan 中保持完成，不得重复副作用。
- `max_replans` 用尽：升级 human/terminal。
- rollback 是回到上一版 ExecutionPlan/ledger checkpoint；真实业务补偿由 Executor 根据 receipt 执行。
- 同一幂等键同 payload 视为成功重放；同 key 不同 payload 为冲突，不得静默换 key 覆盖。
- 只有工具返回 `SUCCESS` 且包含对应 receipt/evidence 时才能声明写入或验证成功。
