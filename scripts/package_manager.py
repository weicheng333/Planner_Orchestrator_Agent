#!/usr/bin/env python3
"""Planner & Orchestrator Agent 的全局/项目安装与卸载。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

from merge_codex_config import install_config, uninstall_config

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PYTHON_PACKAGE_ROOT = PACKAGE_ROOT / "mcp" / "planner_orchestrator-mcp"
VERSION = "1.0.0"


class PackageManagerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    scope: Literal["global", "project"]
    codex_root: Path
    agents_root: Path
    install_root: Path
    runtime: Path
    data: Path
    agent: Path
    skill: Path
    config: Path
    manifest: Path


def resolve_layout(scope: Literal["global", "project"], project_root: Path | None = None) -> Layout:
    if scope == "global":
        codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
        agents_root = Path(os.environ.get("AGENTS_HOME", Path.home() / ".agents")).expanduser()
        data = Path(os.environ.get("PLANNER_ORCHESTRATOR_DATA_DIR", Path.home() / ".local" / "share" / "planner-orchestrator-agent")).expanduser()
    else:
        root = (project_root or Path.cwd()).expanduser().resolve()
        codex_root, agents_root = root / ".codex", root / ".agents"
        data = codex_root / "planner-orchestrator-agent" / "data"
    install_root = codex_root / "planner-orchestrator-agent"
    return Layout(
        scope, codex_root, agents_root, install_root, install_root / "runtime", data,
        codex_root / "agents" / "planner_orchestrator.toml",
        agents_root / "skills" / "planner-orchestration",
        codex_root / "config.toml", install_root / "install-manifest.json",
    )


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise PackageManagerError(f"拒绝覆盖符号链接：{path}")


def _replace_file(source: Path, destination: Path) -> Path | None:
    _reject_symlink(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destination.exists():
        backup = destination.with_name(f".{destination.name}.backup-{uuid4().hex}")
        os.replace(destination, backup)
    temporary = destination.with_name(f".{destination.name}.new-{uuid4().hex}")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        if backup:
            os.replace(backup, destination)
        raise
    return backup


def _replace_directory(source: Path, destination: Path) -> Path | None:
    _reject_symlink(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.new-{uuid4().hex}"
    shutil.copytree(source, temporary)
    backup = None
    try:
        if destination.exists():
            backup = destination.parent / f".{destination.name}.backup-{uuid4().hex}"
            os.replace(destination, backup)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if backup and not destination.exists():
            os.replace(backup, destination)
        raise
    return backup


def _restore_replacement(destination: Path, backup: Path | None) -> None:
    """撤销一次成功的替换；只处理安装器已明确记录的目标。"""
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if backup is not None and backup.exists():
        os.replace(backup, destination)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _build_runtime(source: Path, destination: Path, python: Path) -> Path | None:
    _reject_symlink(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".planner-runtime-", dir=destination.parent))
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(source / name, staging / name)
    shutil.copytree(source / "src", staging / "src")
    backup = None
    try:
        if destination.exists():
            backup = destination.parent / f".{destination.name}.backup-{uuid4().hex}"
            os.replace(destination, backup)
        os.replace(staging, destination)
        subprocess.run([str(python), "-m", "venv", str(destination / ".venv")], check=True)
        subprocess.run([str(destination / ".venv" / "bin" / "python"), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", str(destination)], check=True)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        if backup:
            os.replace(backup, destination)
        raise
    return backup


RuntimeBuilder = Callable[[Path, Path, Path], Path | None]


def install_package(layout: Layout, python: Path, *, runtime_builder: RuntimeBuilder = _build_runtime) -> dict:
    required = [PYTHON_PACKAGE_ROOT / "pyproject.toml", PACKAGE_ROOT / ".codex" / "agents" / "planner_orchestrator.toml", PACKAGE_ROOT / ".agents" / "skills" / "planner-orchestration" / "SKILL.md"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise PackageManagerError(f"安装包缺少文件：{missing}")
    layout.install_root.mkdir(parents=True, exist_ok=True)
    layout.data.mkdir(parents=True, exist_ok=True)
    original_config = layout.config.read_bytes() if layout.config.exists() else None
    replacements: list[tuple[Path, Path | None]] = []
    try:
        replacements.append((layout.runtime, runtime_builder(PYTHON_PACKAGE_ROOT, layout.runtime, python)))
        replacements.append((layout.agent, _replace_file(PACKAGE_ROOT / ".codex" / "agents" / "planner_orchestrator.toml", layout.agent)))
        replacements.append((layout.skill, _replace_directory(PACKAGE_ROOT / ".agents" / "skills" / "planner-orchestration", layout.skill)))
        install_config(layout.config, runtime_python=layout.runtime / ".venv" / "bin" / "python", runtime_directory=layout.runtime, data_directory=layout.data)
        manifest = {
            "version": VERSION, "scope": layout.scope,
            "paths": {"runtime": str(layout.runtime), "data": str(layout.data), "agent": str(layout.agent), "skill": str(layout.skill), "config": str(layout.config)},
            "ownership": {"agent_sha256": _hash_file(layout.agent), "skill_sha256": _hash_tree(layout.skill)},
        }
        _atomic_json(layout.manifest, manifest)
    except Exception:
        if original_config is None:
            layout.config.unlink(missing_ok=True)
        else:
            layout.config.parent.mkdir(parents=True, exist_ok=True)
            layout.config.write_bytes(original_config)
        for destination, backup in reversed(replacements):
            _restore_replacement(destination, backup)
        layout.manifest.unlink(missing_ok=True)
        raise
    for _, backup in replacements:
        if backup:
            shutil.rmtree(backup) if backup.is_dir() else backup.unlink(missing_ok=True)
    return manifest


def uninstall_package(layout: Layout, *, purge_data: bool = False) -> list[str]:
    messages: list[str] = []
    manifest = json.loads(layout.manifest.read_text(encoding="utf-8")) if layout.manifest.exists() else None
    uninstall_config(layout.config)
    if manifest is None:
        return ["未找到安装清单；未删除 Agent、Skill、runtime 或数据"]
    ownership = manifest.get("ownership", {})
    if layout.agent.exists() and _hash_file(layout.agent) == ownership.get("agent_sha256"):
        layout.agent.unlink()
    elif layout.agent.exists():
        messages.append(f"Agent 已被修改，保留：{layout.agent}")
    if layout.skill.exists() and _hash_tree(layout.skill) == ownership.get("skill_sha256"):
        shutil.rmtree(layout.skill)
    elif layout.skill.exists():
        messages.append(f"Skill 已被修改，保留：{layout.skill}")
    if layout.runtime.exists():
        shutil.rmtree(layout.runtime)
    layout.manifest.unlink(missing_ok=True)
    if purge_data and layout.data.exists():
        if layout.data.resolve() in {Path.home().resolve(), Path("/")}:
            raise PackageManagerError("拒绝删除宽泛数据目录")
        shutil.rmtree(layout.data)
    return messages


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    install = sub.add_parser("install")
    install.add_argument("--scope", choices=["global", "project"], required=True)
    install.add_argument("--project-root", type=Path)
    install.add_argument("--python", type=Path, required=True)
    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--scope", choices=["global", "project"], required=True)
    uninstall.add_argument("--project-root", type=Path)
    uninstall.add_argument("--purge-data", action="store_true")
    args = parser.parse_args()
    layout = resolve_layout(args.scope, args.project_root)
    if args.action == "install":
        print(json.dumps(install_package(layout, args.python), ensure_ascii=False, indent=2))
    else:
        for message in uninstall_package(layout, purge_data=args.purge_data):
            print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
