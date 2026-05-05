# SPDX-License-Identifier: MIT
"""
Host configuration manager.
Registers / unregisters MCP servers in Claude Code (~/.claude.json)
and Codex (~/.codex/config.toml).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

from .models import SkillManifest

# ────────────────────────────────────────────────────────────────────────── #
# Config paths (can be overridden by env vars for testing)                   #
# ────────────────────────────────────────────────────────────────────────────#
import os

CLAUDE_CONFIG   = Path(os.environ.get("CLAUDE_CONFIG_PATH",   str(Path.home() / ".claude.json")))
CODEX_CONFIG    = Path(os.environ.get("CODEX_CONFIG_PATH",    str(Path.home() / ".codex" / "config.toml")))


# ────────────────────────────────────────────────────────────────────────── #
# Helpers                                                                     #
# ────────────────────────────────────────────────────────────────────────────#

def _mcp_entry(manifest: SkillManifest) -> Dict[str, Any]:
    """Build the MCP server entry dict for this skill."""
    if manifest.mcp.command:
        command = manifest.mcp.command
        args = list(manifest.mcp.args)
    elif manifest.runtime.type == "python":
        python = manifest.venv_python
        command = str(python) if python else "python3"
        args = [str(manifest.entrypoint_path)] + manifest.mcp.args
    elif manifest.runtime.type == "node":
        command = "node"
        args = [str(manifest.entrypoint_path)] + manifest.mcp.args
    else:
        command = str(manifest.entrypoint_path)
        args = list(manifest.mcp.args)

    return {
        "type":    manifest.mcp.transport,
        "command": command,
        "args":    args,
        "env":     manifest.mcp.env,
    }


# ────────────────────────────────────────────────────────────────────────── #
# Claude Code  (~/.claude.json)                                               #
# ────────────────────────────────────────────────────────────────────────────#

def _load_claude() -> Dict[str, Any]:
    if CLAUDE_CONFIG.exists():
        return json.loads(CLAUDE_CONFIG.read_text())
    return {}


def _save_claude(data: Dict[str, Any]) -> None:
    CLAUDE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_CONFIG.write_text(json.dumps(data, indent=2))


def register_claude(manifest: SkillManifest) -> None:
    data = _load_claude()
    data.setdefault("mcpServers", {})[manifest.name] = _mcp_entry(manifest)
    _save_claude(data)


def unregister_claude(name: str) -> bool:
    data = _load_claude()
    servers = data.get("mcpServers", {})
    if name in servers:
        del servers[name]
        _save_claude(data)
        return True
    return False


def is_registered_claude(name: str) -> bool:
    return name in _load_claude().get("mcpServers", {})


# ────────────────────────────────────────────────────────────────────────── #
# Codex  (~/.codex/config.toml)                                               #
# ────────────────────────────────────────────────────────────────────────────#

def _load_codex() -> Dict[str, Any]:
    if CODEX_CONFIG.exists():
        with open(CODEX_CONFIG, "rb") as f:
            return tomllib.load(f)
    return {}


def _save_codex(data: Dict[str, Any]) -> None:
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(CODEX_CONFIG, "wb") as f:
        tomli_w.dump(data, f)


def register_codex(manifest: SkillManifest) -> None:
    data = _load_codex()
    entry = _mcp_entry(manifest)
    data.setdefault("mcp_servers", {})[manifest.name] = {
        "command": entry["command"],
        "args":    entry["args"],
        "env":     entry["env"],
    }
    _save_codex(data)


def unregister_codex(name: str) -> bool:
    data = _load_codex()
    servers = data.get("mcp_servers", {})
    if name in servers:
        del servers[name]
        _save_codex(data)
        return True
    return False


def is_registered_codex(name: str) -> bool:
    return name in _load_codex().get("mcp_servers", {})


# ────────────────────────────────────────────────────────────────────────── #
# Unified API                                                                 #
# ────────────────────────────────────────────────────────────────────────────#

def register(manifest: SkillManifest, targets: Optional[List[str]] = None) -> Dict[str, bool]:
    """
    Register a skill to specified hosts (default: all enabled in manifest).
    Description-only skills (runtime.type="none") skip MCP registration
    but still get native skill entries via _post_install.
    Returns {host: success} mapping.
    """
    if manifest.runtime.type == "none":
        return {"claude_code": True, "codex": True}

    want = set(targets) if targets else set()
    if not want:
        if manifest.hosts.claude_code:
            want.add("claude_code")
        if manifest.hosts.codex:
            want.add("codex")

    result: Dict[str, bool] = {}
    for host in want:
        try:
            if host == "claude_code":
                register_claude(manifest)
                result["claude_code"] = True
            elif host == "codex":
                register_codex(manifest)
                result["codex"] = True
        except Exception as e:
            result[host] = False
    return result


def unregister(name: str, targets: Optional[List[str]] = None) -> Dict[str, bool]:
    hosts = set(targets) if targets else {"claude_code", "codex"}
    result: Dict[str, bool] = {}
    for host in hosts:
        if host == "claude_code":
            result["claude_code"] = unregister_claude(name)
        elif host == "codex":
            result["codex"] = unregister_codex(name)
    return result


def registration_status(name: str) -> Dict[str, bool]:
    return {
        "claude_code": is_registered_claude(name),
        "codex":       is_registered_codex(name),
    }
