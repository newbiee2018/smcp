"""
Shared fixtures for integration tests.
"""
import importlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def isolated_smcp_env(tmp_path):
    """
    Provides a fully isolated skill-mcp environment:
    - Fresh XDG_DATA_HOME in tmp (clean registry + skills dir)
    - Writable claude.json and codex config.toml in tmp
    - Reloads host_config and registry modules to pick up new paths
    """
    data_home = tmp_path / "data"
    data_home.mkdir()
    config_home = tmp_path / "config"
    config_home.mkdir()

    claude_json = tmp_path / "claude.json"
    claude_json.write_text("{}")

    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    codex_toml = codex_dir / "config.toml"
    codex_toml.write_text("")

    old_env = {}
    env_vars = {
        "XDG_DATA_HOME": str(data_home),
        "XDG_CONFIG_HOME": str(config_home),
        "CLAUDE_CONFIG_PATH": str(claude_json),
        "CODEX_CONFIG_PATH": str(codex_toml),
    }
    for k, v in env_vars.items():
        old_env[k] = os.environ.get(k)
        os.environ[k] = v

    import src.manager.registry as reg_mod
    import src.manager.host_config as hc_mod
    reg_mod._registry = None
    importlib.reload(reg_mod)
    importlib.reload(hc_mod)

    yield {
        "data_home": data_home,
        "config_home": config_home,
        "claude_json": claude_json,
        "codex_toml": codex_toml,
        "skills_dir": data_home / "skill-mcp" / "skills",
        "exports_dir": data_home / "skill-mcp" / "exports",
    }

    for k, v in old_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    reg_mod._registry = None
    importlib.reload(reg_mod)
    importlib.reload(hc_mod)


@pytest.fixture
def sample_python_skill(tmp_path):
    """
    Creates a minimal Python skill directory with:
    - skill.toml (python runtime, python_version=3.10)
    - requirements.txt (requests>=2.0.0)
    - src/main.py (stub MCP server)
    Returns the path.
    """
    skill_dir = tmp_path / "sample-python-skill"
    skill_dir.mkdir()
    (skill_dir / "src").mkdir()

    import tomli_w
    manifest = {
        "skill": {
            "name": "sample-python-skill",
            "version": "1.0.0",
            "description": "A test Python skill",
            "author": "test",
            "tags": ["test"],
        },
        "runtime": {
            "type": "python",
            "python_version": "3.10",
            "install_cmd": "pip install -r requirements.txt",
        },
        "mcp": {
            "entrypoint": "src/main.py",
            "transport": "stdio",
        },
        "hosts": {
            "claude_code": True,
            "codex": True,
        },
    }
    with open(skill_dir / "skill.toml", "wb") as f:
        tomli_w.dump(manifest, f)

    (skill_dir / "requirements.txt").write_text("requests>=2.0.0\n")
    (skill_dir / "src" / "main.py").write_text(
        '#!/usr/bin/env python3\n'
        'import requests\n'
        'print("sample MCP server stub")\n'
    )

    return skill_dir
