"""
Shared fixtures for tests.

IMPORTANT: The `_guard_real_configs` fixture runs automatically for every test
session.  It redirects CLAUDE_CONFIG_PATH, CODEX_CONFIG_PATH, CODEX_HOME, and
HOME to temp paths so that a broken test can never pollute the user's real
~/.claude.json, ~/.codex/config.toml, or native skill directories.
"""
import importlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────────── #
# Session-level guard: redirect all config writes to temp dir                 #
# ────────────────────────────────────────────────────────────────────────────#

@pytest.fixture(autouse=True, scope="session")
def _guard_real_configs(tmp_path_factory):
    """
    Prevents any test from writing to real host configs.
    Sets env vars BEFORE any manager module is imported.
    """
    guard_dir = tmp_path_factory.mktemp("config_guard")

    claude_json = guard_dir / "claude.json"
    claude_json.write_text("{}")

    codex_dir = guard_dir / "codex"
    codex_dir.mkdir()
    codex_toml = codex_dir / "config.toml"
    codex_toml.write_text("")

    codex_home = guard_dir / "codex_home"
    codex_home.mkdir()

    fake_home = guard_dir / "fakehome"
    fake_home.mkdir()

    saved = {}
    guard_vars = {
        "CLAUDE_CONFIG_PATH": str(claude_json),
        "CODEX_CONFIG_PATH": str(codex_toml),
        "CODEX_HOME": str(codex_home),
        "XDG_DATA_HOME": str(guard_dir / "data"),
        "XDG_CONFIG_HOME": str(guard_dir / "config"),
    }
    for k, v in guard_vars.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v

    yield

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ────────────────────────────────────────────────────────────────────────── #
# Per-test isolated environment                                               #
# ────────────────────────────────────────────────────────────────────────────#

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

    import manager.registry as reg_mod
    import manager.host_config as hc_mod
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
