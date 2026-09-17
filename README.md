# Planner & Orchestrator Agent

`planner_orchestrator` 把已经确认的 `TaskSpec` 转成最小充分执行 DAG，选择 single model、single agent + tools 或 multi-agent 策略，并维护版本化 ExecutionPlan 与进度账本。

本项目只负责规划、路由、预算、权限门、终止条件和 replan；不替代 Research、Executor 或 Verifier 执行任务。

## 1.1.0 技术方案门

Planner 在拆解任务前主动检查相关技术选型，比较可行方案并说明取舍、费用依据与推荐；外部事实交 Research 取证。用户确认技术方案不等于授权开发或部署。若选型改变产品需求，返回 Intake 修订。

ExecutionPlan 新增可选 technical_review 与节点 technical_decision_ids。新规划须显式记录审查；历史计划仍可读取，数据库无需迁移。已有未定选型且包含 executor 的完整计划不能标记 READY；研究阶段可独立规划。MCP 校验结构、证据引用及状态门，不保证模型已经穷尽维度，也不独立证明确认引用的真实性。

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
