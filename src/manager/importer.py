"""
Importer — unpacks a .skill.tar.gz archive into the global skills directory,
creates the runtime environment, and registers with host configs.

Import workflow
───────────────
1. Extract archive → SKILL_MCP_SKILLS/<name>/
2. Read skill.toml
3. Create venv / install deps  (runtime.create_env)
4. Register with Claude Code + Codex  (host_config.register)
5. Add to registry  (registry.register)

This module is also what an AI agent executes when it reads agent-setup.json
and decides to install programmatically via the MCP tool `skill_import`.
"""
from __future__ import annotations

import json
import os
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .models import SkillManifest
from .registry import SKILL_MCP_SKILLS, get_registry
from . import runtime as rt_mgr
from . import host_config


@dataclass
class ImportResult:
    success: bool
    skill_name: str
    install_path: Optional[Path]
    env_created: bool
    hosts_registered: Dict[str, bool]
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":          self.success,
            "skill_name":       self.skill_name,
            "install_path":     str(self.install_path) if self.install_path else None,
            "env_created":      self.env_created,
            "hosts_registered": self.hosts_registered,
            "message":          self.message,
        }


def import_skill(
    package_path: Path,
    install_dir: Optional[Path] = None,
    rebuild_env: bool = True,
    register_hosts: bool = True,
) -> ImportResult:
    """
    Import a skill from a .skill.tar.gz archive.

    Parameters
    ----------
    package_path  : path to the .skill.tar.gz file
    install_dir   : where to unpack (default: SKILL_MCP_SKILLS/<name>)
    rebuild_env   : if True, destroy existing venv and recreate
    register_hosts: if True, register with Claude Code / Codex

    Returns an ImportResult describing what happened.
    """
    package_path = Path(package_path).expanduser().resolve()
    if not package_path.exists():
        return ImportResult(
            success=False,
            skill_name="unknown",
            install_path=None,
            env_created=False,
            hosts_registered={},
            message=f"Package not found: {package_path}",
        )

    # ── Step 1: Read the manifest inside the archive ────────────────────
    try:
        manifest_data = _read_manifest_from_archive(package_path)
    except Exception as e:
        return ImportResult(
            success=False,
            skill_name="unknown",
            install_path=None,
            env_created=False,
            hosts_registered={},
            message=f"Failed to read skill.toml from archive: {e}",
        )

    skill_name = manifest_data["skill"]["name"]
    skill_ver  = manifest_data["skill"]["version"]

    # ── Step 2: Determine install path ──────────────────────────────────
    target_dir = (install_dir or SKILL_MCP_SKILLS) / skill_name
    target_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 3: Extract archive ─────────────────────────────────────────
    try:
        _extract(package_path, target_dir)
    except Exception as e:
        return ImportResult(
            success=False,
            skill_name=skill_name,
            install_path=target_dir,
            env_created=False,
            hosts_registered={},
            message=f"Extraction failed: {e}",
        )

    # ── Step 4: Parse full manifest ─────────────────────────────────────
    toml_path = target_dir / "skill.toml"
    manifest = SkillManifest.from_toml(toml_path)
    manifest.install_path = target_dir

    # ── Step 5: Build runtime environment ──────────────────────────────
    env_created = False
    try:
        if rebuild_env:
            rt_mgr.rebuild_env(manifest)
        else:
            rt_mgr.create_env(manifest)
        env_created = True
    except Exception as e:
        return ImportResult(
            success=False,
            skill_name=skill_name,
            install_path=target_dir,
            env_created=False,
            hosts_registered={},
            message=f"Runtime creation failed: {e}",
        )

    # ── Step 6: Register with host configs ──────────────────────────────
    hosts_registered: Dict[str, bool] = {}
    if register_hosts:
        try:
            hosts_registered = host_config.register(manifest)
        except Exception as e:
            hosts_registered = {"error": str(e)}  # type: ignore[assignment]

    # ── Step 7: Add to registry ─────────────────────────────────────────
    reg = get_registry()
    reg.register(manifest)
    reg.mark_env_ready(skill_name, env_created)

    # ── Step 8: Install native skill entries + CLI wrapper ─────────────
    _post_install(manifest)

    return ImportResult(
        success=True,
        skill_name=skill_name,
        install_path=target_dir,
        env_created=env_created,
        hosts_registered=hosts_registered,
        message=f"Skill '{skill_name}' v{skill_ver} installed at {target_dir}",
    )


def import_from_dir(
    source_dir: Path,
    rebuild_env: bool = True,
    register_hosts: bool = True,
) -> ImportResult:
    """
    Install a skill directly from a local source directory
    (e.g. a draft workspace).  Copies files to the global skills dir.
    """
    source_dir = Path(source_dir).expanduser().resolve()
    toml_path = source_dir / "skill.toml"

    if not toml_path.exists():
        return ImportResult(
            success=False,
            skill_name="unknown",
            install_path=None,
            env_created=False,
            hosts_registered={},
            message=f"No skill.toml found in {source_dir}",
        )

    manifest = SkillManifest.from_toml(toml_path)
    skill_name = manifest.name

    target_dir = SKILL_MCP_SKILLS / skill_name
    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Copy source → global dir, excluding env dirs
    _copy_skill_dir(source_dir, target_dir)

    manifest.install_path = target_dir

    env_created = False
    try:
        if rebuild_env:
            rt_mgr.rebuild_env(manifest)
        else:
            rt_mgr.create_env(manifest)
        env_created = True
    except Exception as e:
        return ImportResult(
            success=False,
            skill_name=skill_name,
            install_path=target_dir,
            env_created=False,
            hosts_registered={},
            message=f"Runtime creation failed: {e}",
        )

    hosts_registered: Dict[str, bool] = {}
    if register_hosts:
        hosts_registered = host_config.register(manifest)

    reg = get_registry()
    reg.register(manifest)
    reg.mark_env_ready(skill_name, env_created)

    _post_install(manifest)

    return ImportResult(
        success=True,
        skill_name=skill_name,
        install_path=target_dir,
        env_created=env_created,
        hosts_registered=hosts_registered,
        message=f"Skill '{skill_name}' v{manifest.version} installed from {source_dir}",
    )


# ────────────────────────────────────────────────────────────────────────── #
# Post-install: native skill entries + CLI wrapper                             #
# ────────────────────────────────────────────────────────────────────────────#

def _post_install(manifest: SkillManifest) -> None:
    """Install native skill entries for Codex and Claude Code, plus CLI wrapper."""
    skill_dir = manifest.install_path
    if not skill_dir:
        return

    # Install Codex native skill (SKILL.md → ~/.codex/skills/<name>/)
    codex_skill_src = skill_dir / "skills" / "codex" / "SKILL.md"
    if codex_skill_src.exists():
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        codex_skills_dir = codex_home / "skills" / manifest.name
        codex_skills_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(codex_skill_src, codex_skills_dir / "SKILL.md")

    # Install Claude Code native skill (CLAUDE.md → ~/.claude/skills/<name>/)
    claude_skill_src = skill_dir / "skills" / "claude" / "CLAUDE.md"
    if claude_skill_src.exists():
        claude_skills_dir = Path.home() / ".claude" / "skills" / manifest.name
        claude_skills_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(claude_skill_src, claude_skills_dir / "CLAUDE.md")

    # Install CLI wrapper if the skill has a cli.py
    cli_py = skill_dir / "src" / "cli.py"
    if cli_py.exists() and manifest.venv_python:
        bin_dir = Path.home() / ".local" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        wrapper = bin_dir / manifest.name.replace("-", "").replace("_", "")
        # Use a more user-friendly name: smcp
        if manifest.name == "skill-mcp-protocol":
            wrapper = bin_dir / "smcp"
        wrapper.write_text(
            f"#!/usr/bin/env bash\n"
            f'exec "{manifest.venv_python}" "{cli_py}" "$@"\n'
        )
        wrapper.chmod(0o755)


# ────────────────────────────────────────────────────────────────────────── #
# Helpers                                                                     #
# ────────────────────────────────────────────────────────────────────────────#

_SKIP_DIRS = {".venv", "venv", "env", "node_modules", "__pycache__", ".git", "target"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _read_manifest_from_archive(archive: Path) -> dict:
    """Peek inside the archive and return the parsed skill.toml as a dict."""
    import sys
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomllib  # type: ignore[no-redef]
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith("skill.toml"):
                f = tar.extractfile(member)
                if f:
                    return tomllib.load(f)
    raise FileNotFoundError("skill.toml not found inside archive.")


def _extract(archive: Path, target_dir: Path) -> None:
    """Extract archive into target_dir, stripping the top-level directory."""
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        # Strip top-level dir (e.g. "my-skill-1.0.0/src/main.py" → "src/main.py")
        top = members[0].name.split("/")[0] if members else ""
        for member in members:
            if member.name == top:
                continue
            stripped = member.name[len(top) + 1:]  # remove "topdir/"
            if not stripped:
                continue
            member.name = stripped
            tar.extract(member, path=target_dir)


def _copy_skill_dir(src: Path, dst: Path) -> None:
    """Recursively copy src → dst, skipping env dirs."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in _SKIP_DIRS:
            continue
        if item.is_dir():
            _copy_skill_dir(item, dst / item.name)
        elif item.suffix not in _SKIP_SUFFIXES:
            shutil.copy2(item, dst / item.name)
