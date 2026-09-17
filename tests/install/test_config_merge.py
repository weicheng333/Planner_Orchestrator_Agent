from pathlib import Path

import pytest

from merge_codex_config import ConfigMergeError, TABLE_NAME, install_config, uninstall_config


def test_config_install_is_idempotent_and_preserves_user_content(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[projects."/tmp/demo"]\ntrust_level = "trusted"\n', encoding="utf-8")
    kwargs = {
        "runtime_python": tmp_path / "runtime/.venv/bin/python",
        "runtime_directory": tmp_path / "runtime",
        "data_directory": tmp_path / "data",
    }
    install_config(config, **kwargs)
    first = config.read_text(encoding="utf-8")
    install_config(config, **kwargs)
    assert config.read_text(encoding="utf-8") == first
    assert "trust_level" in first
    assert TABLE_NAME in first
    uninstall_config(config)
    assert "trust_level" in config.read_text(encoding="utf-8")
    assert TABLE_NAME not in config.read_text(encoding="utf-8")


def test_config_refuses_unowned_server_table(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(f"[mcp_servers.{TABLE_NAME}]\ncommand = 'other'\n", encoding="utf-8")
    with pytest.raises(ConfigMergeError):
        install_config(
            config,
            runtime_python=tmp_path / "python",
            runtime_directory=tmp_path / "runtime",
            data_directory=tmp_path / "data",
        )
