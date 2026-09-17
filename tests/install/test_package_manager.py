from pathlib import Path

import pytest

from package_manager import install_package, resolve_layout, uninstall_package


def _fake_runtime(source: Path, destination: Path, python: Path) -> Path | None:
    destination.mkdir(parents=True)
    executable = destination / ".venv/bin/python"
    executable.parent.mkdir(parents=True)
    executable.write_text("runtime", encoding="utf-8")
    return None


def test_project_install_and_uninstall_preserve_data(tmp_path: Path) -> None:
    layout = resolve_layout("project", tmp_path)
    manifest = install_package(layout, Path("/usr/bin/python3"), runtime_builder=_fake_runtime)
    assert manifest["version"] == "1.1.0"
    assert layout.agent.exists() and layout.skill.exists() and layout.manifest.exists()
    sentinel = layout.data / "keep.txt"
    sentinel.write_text("user data", encoding="utf-8")
    uninstall_package(layout)
    assert sentinel.read_text(encoding="utf-8") == "user data"
    assert not layout.agent.exists()
    assert not layout.skill.exists()


def test_install_rolls_back_all_replacements_on_config_conflict(tmp_path: Path) -> None:
    layout = resolve_layout("project", tmp_path)
    layout.agent.parent.mkdir(parents=True)
    layout.agent.write_text("original agent", encoding="utf-8")
    layout.skill.mkdir(parents=True)
    (layout.skill / "SKILL.md").write_text("original skill", encoding="utf-8")
    layout.config.parent.mkdir(parents=True, exist_ok=True)
    layout.config.write_text("[mcp_servers.planner_orchestrator_mcp]\ncommand='foreign'\n", encoding="utf-8")
    with pytest.raises(Exception):
        install_package(layout, Path("/usr/bin/python3"), runtime_builder=_fake_runtime)
    assert layout.agent.read_text(encoding="utf-8") == "original agent"
    assert (layout.skill / "SKILL.md").read_text(encoding="utf-8") == "original skill"
    assert not layout.runtime.exists()
    assert not layout.manifest.exists()
