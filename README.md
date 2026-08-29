# Planner & Orchestrator Agent

`planner_orchestrator` 把已经确认的 `TaskSpec` 转成最小充分执行 DAG，选择 single model、single agent + tools 或 multi-agent 策略，并维护版本化 ExecutionPlan 与进度账本。

本项目只负责规划、路由、预算、权限门、终止条件和 replan；不替代 Research、Executor 或 Verifier 执行任务。

## 组成

- `.codex/agents/planner_orchestrator.toml`：Custom Agent
- `.agents/skills/planner-orchestration/`：规划 Skill 与按需 references
- `mcp/planner_orchestrator-mcp/`：本地 Python STDIO MCP
- `contracts/`：跨 Agent JSON Schema
- `scripts/`：全局/项目安装与安全卸载
- `tests/`：路由、契约、MCP、存储、失败注入和对抗测试

## 开发与测试

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e 'mcp/planner_orchestrator-mcp[dev]'
.venv/bin/python -m pytest
```

导出合同：

```bash
.venv/bin/planner-orchestrator-export-schemas
```

## 安装

```bash
scripts/install-global.sh
scripts/install-project.sh /ABSOLUTE/PATH/TO/PROJECT
```

默认运行数据位于 `~/.local/share/planner-orchestrator-agent/`。普通卸载保留 SQLite 数据；只有显式 `--purge-data` 才清理本包运行数据。

该安装器只管理 `planner_orchestrator` Agent、`planner-orchestration` Skill、`planner_orchestrator_mcp` 配置区块和本包 runtime，不覆盖其他 Codex 配置。
