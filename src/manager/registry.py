# SPDX-License-Identifier: MIT
"""
Local skill registry.
Follows XDG Base Directory Specification:
  Data (skills, registry):  $XDG_DATA_HOME/skill-mcp/   → ~/.local/share/skill-mcp/
  Config:                   $XDG_CONFIG_HOME/skill-mcp/ → ~/.config/skill-mcp/
  Exports:                  $XDG_DATA_HOME/skill-mcp/exports/

The local workspace (where you develop/test a skill) stays a draft until
you run `smcp install <path>` which copies it into the global data dir.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
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

# ── XDG paths ──────────────────────────────────────────────────────────────
_XDG_DATA   = Path(os.environ.get("XDG_DATA_HOME",   str(Path.home() / ".local" / "share")))
_XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))

SKILL_MCP_DATA    = _XDG_DATA   / "skill-mcp"   # registry + installed skills
SKILL_MCP_CONFIG  = _XDG_CONFIG / "skill-mcp"   # user config
SKILL_MCP_SKILLS  = SKILL_MCP_DATA / "skills"   # each skill lives in its own subdir
SKILL_MCP_EXPORTS = SKILL_MCP_DATA / "exports"  # .skill.tar.gz packages

_REGISTRY_FILE = SKILL_MCP_DATA / "registry.toml"


# ────────────────────────────────────────────────────────────────────────── #
# Registry                                                                    #
# ────────────────────────────────────────────────────────────────────────────#

class Registry:
    def __init__(self, path: Path = _REGISTRY_FILE) -> None:
        self.path = path
        self._data: Dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # I/O                                                                  #
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path, "rb") as f:
                self._data = tomllib.load(f)
        else:
            self._data = {"skills": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as f:
            tomli_w.dump(self._data, f)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def register(self, manifest: SkillManifest) -> None:
        """Add or update a skill entry in the registry."""
        assert manifest.install_path, "Skill must have an install_path."
        skills = self._data.setdefault("skills", {})
        skills[manifest.name] = {
            "name":         manifest.name,
            "version":      manifest.version,
            "install_path": str(manifest.install_path),
            "runtime_type": manifest.runtime.type,
            "env_ready":    manifest.env_ready,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "hosts": {
                "claude_code": manifest.hosts.claude_code,
                "codex":       manifest.hosts.codex,
            },
        }
        self._save()

    def unregister(self, name: str) -> bool:
        """Remove a skill from the registry. Returns True if it was present."""
        skills = self._data.get("skills", {})
        if name in skills:
            del skills[name]
            self._save()
            return True
        return False

    def get(self, name: str) -> Optional[SkillManifest]:
        """Load and return the SkillManifest for a registered skill."""
        entry = self._data.get("skills", {}).get(name)
        if not entry:
            return None
        install_path = Path(entry["install_path"])
        toml_file = install_path / "skill.toml"
        if not toml_file.exists():
            return None
        manifest = SkillManifest.from_toml(toml_file)
        manifest.install_path = install_path
        return manifest

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all registry entries as plain dicts."""
        return list(self._data.get("skills", {}).values())

    def exists(self, name: str) -> bool:
        return name in self._data.get("skills", {})

    def mark_env_ready(self, name: str, ready: bool) -> None:
        entry = self._data.get("skills", {}).get(name)
        if entry:
            entry["env_ready"] = ready
            self._save()


# Module-level singleton
_registry: Optional[Registry] = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry
