#!/usr/bin/env python3
"""安全合并或移除 planner_orchestrator_mcp 配置。"""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

BEGIN_MARKER = "# BEGIN planner-orchestrator-agent managed MCP"
END_MARKER = "# END planner-orchestrator-agent managed MCP"
TABLE_NAME = "planner_orchestrator_mcp"


class ConfigMergeError(RuntimeError):
    pass


def _parse(content: str, path: Path) -> dict:
    try:
        return tomllib.loads(content) if content.strip() else {}
    except tomllib.TOMLDecodeError as error:
        raise ConfigMergeError(f"无法安全解析 TOML：{path}：{error}") from error


def _span(content: str) -> tuple[int, int] | None:
    begins, ends = content.count(BEGIN_MARKER), content.count(END_MARKER)
    if begins != ends or begins > 1:
        raise ConfigMergeError("Planner MCP 配置所有权标记不完整或重复")
    if begins == 0:
        return None
    start = content.index(BEGIN_MARKER)
    end = content.index(END_MARKER, start) + len(END_MARKER)
    while end < len(content) and content[end] in "\r\n":
        end += 1
    return start, end


def _render(runtime_python: Path, runtime_directory: Path, data_directory: Path) -> str:
    quote = lambda value: json.dumps(str(value), ensure_ascii=False)
    return "\n".join([
        BEGIN_MARKER,
        f"[mcp_servers.{TABLE_NAME}]",
        f"command = {quote(runtime_python)}",
        'args = ["-m", "planner_orchestrator_agent.mcp_server.server"]',
        f"cwd = {quote(runtime_directory)}",
        f"env = {{ PLANNER_ORCHESTRATOR_DATA_DIR = {quote(data_directory)} }}",
        "enabled = true",
        "startup_timeout_sec = 20",
        "tool_timeout_sec = 45",
        'default_tools_approval_mode = "writes"',
        END_MARKER,
        "",
    ])


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.name}.bak.planner-orchestrator.{suffix}")
    backup.write_bytes(path.read_bytes())
    return backup


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install_config(path: Path, *, runtime_python: Path, runtime_directory: Path, data_directory: Path) -> Path | None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    parsed = _parse(original, path)
    span = _span(original)
    if span is None and TABLE_NAME in parsed.get("mcp_servers", {}):
        raise ConfigMergeError(f"{path} 已有非本安装器管理的 mcp_servers.{TABLE_NAME}，拒绝覆盖")
    block = _render(runtime_python, runtime_directory, data_directory)
    if span is None:
        prefix = original
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        updated = prefix + block
    else:
        updated = original[:span[0]] + block + original[span[1]:]
    _parse(updated, path)
    if updated == original:
        return None
    backup = _backup(path)
    _atomic_write(path, updated)
    return backup


def uninstall_config(path: Path) -> Path | None:
    if not path.exists():
        return None
    original = path.read_text(encoding="utf-8")
    _parse(original, path)
    span = _span(original)
    if span is None:
        return None
    updated = (original[:span[0]] + original[span[1]:]).rstrip()
    updated = updated + "\n" if updated else ""
    _parse(updated, path)
    backup = _backup(path)
    _atomic_write(path, updated)
    return backup
