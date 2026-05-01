"""
GitHub installer — clone a repo, detect project type, generate skill.toml,
build runtime, and register with hosts.

Supports:
  - Node.js projects (package.json → npm install)
  - Python projects (requirements.txt / pyproject.toml → venv)
  - Rust/binary projects (Cargo.toml → cargo build --release)
  - Pre-built binaries (download from GitHub Releases)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tomli_w

from .importer import ImportResult, import_from_dir
from .models import SkillManifest


def _run(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def _parse_github_url(url: str) -> Tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL."""
    url = url.rstrip("/").rstrip(".git")
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not m:
        raise ValueError(f"Not a valid GitHub URL: {url}")
    return m.group(1), m.group(2)


def _clone(url: str, dest: Path) -> None:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git not found on PATH.")
    _run([git, "clone", "--depth", "1", url, str(dest)])


def _detect_project_type(repo_dir: Path) -> Tuple[str, Dict[str, Any]]:
    """
    Inspect a cloned repo and return (runtime_type, metadata).
    runtime_type: "node", "python", or "binary"
    """
    if (repo_dir / "package.json").exists():
        with open(repo_dir / "package.json") as f:
            pkg = json.load(f)
        return "node", {"package_json": pkg}

    if (repo_dir / "Cargo.toml").exists():
        return "binary", {"build_system": "cargo"}

    if (repo_dir / "requirements.txt").exists():
        return "python", {"deps_file": "requirements.txt"}

    if (repo_dir / "pyproject.toml").exists():
        return "python", {"deps_file": "pyproject.toml"}

    raise RuntimeError(
        f"Cannot detect project type in {repo_dir}. "
        "No package.json, Cargo.toml, requirements.txt, or pyproject.toml found."
    )


def _find_node_entrypoint(repo_dir: Path, pkg: Dict[str, Any]) -> str:
    """Determine the MCP server entrypoint for a Node.js project."""
    if "bin" in pkg:
        bins = pkg["bin"]
        if isinstance(bins, str):
            return bins
        if isinstance(bins, dict):
            for name, path in bins.items():
                if "mcp" in name.lower() or "server" in name.lower():
                    return path
            return list(bins.values())[0]

    if "main" in pkg:
        return pkg["main"]

    for candidate in ["index.js", "src/index.js", "dist/index.js", "server.js"]:
        if (repo_dir / candidate).exists():
            return candidate

    return "index.js"


def _find_python_entrypoint(repo_dir: Path) -> str:
    """Determine the MCP server entrypoint for a Python project."""
    for candidate in [
        "src/main.py", "main.py", "server.py",
        "src/server.py", "mcp_server.py",
    ]:
        if (repo_dir / candidate).exists():
            return candidate
    return "src/main.py"


def _generate_skill_toml(
    repo_dir: Path,
    name: str,
    runtime_type: str,
    metadata: Dict[str, Any],
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
) -> None:
    """Generate a skill.toml for repos that don't have one."""
    if runtime_type == "node":
        pkg = metadata.get("package_json", {})
        entrypoint = _find_node_entrypoint(repo_dir, pkg)
        description = pkg.get("description", f"MCP server: {name}")
        version = pkg.get("version", "0.1.0")
        install_cmd = "npm install"
    elif runtime_type == "python":
        entrypoint = _find_python_entrypoint(repo_dir)
        description = f"MCP server: {name}"
        version = "0.1.0"
        deps_file = metadata.get("deps_file", "requirements.txt")
        install_cmd = f"pip install -r {deps_file}" if deps_file == "requirements.txt" else "pip install ."
    elif runtime_type == "binary":
        entrypoint = ""
        description = f"MCP server: {name}"
        version = "0.1.0"
        install_cmd = ""
    else:
        raise ValueError(f"Unknown runtime type: {runtime_type}")

    data = {
        "skill": {
            "name": name,
            "version": version,
            "description": description,
            "author": "",
            "tags": ["mcp"],
        },
        "runtime": {
            "type": runtime_type,
            "install_cmd": install_cmd,
        },
        "mcp": {
            "entrypoint": entrypoint,
            "transport": "stdio",
        },
        "hosts": {
            "claude_code": True,
            "codex": True,
        },
    }

    if command:
        data["mcp"]["command"] = command
    if args:
        data["mcp"]["args"] = args

    if runtime_type == "python":
        data["runtime"]["python_version"] = "3.10"

    with open(repo_dir / "skill.toml", "wb") as f:
        tomli_w.dump(data, f)


def install_from_github(
    url: str,
    name_override: Optional[str] = None,
    register_hosts: bool = True,
) -> ImportResult:
    """
    Install an MCP server from a GitHub URL.

    1. Clone the repo (shallow)
    2. Detect project type
    3. Generate skill.toml if absent
    4. Delegate to import_from_dir() for install + env build + registration
    """
    owner, repo = _parse_github_url(url)
    name = name_override or repo

    with tempfile.TemporaryDirectory() as tmp:
        clone_dir = Path(tmp) / repo
        _clone(url, clone_dir)

        if not (clone_dir / "skill.toml").exists():
            runtime_type, metadata = _detect_project_type(clone_dir)
            _generate_skill_toml(clone_dir, name, runtime_type, metadata)

        return import_from_dir(
            source_dir=clone_dir,
            rebuild_env=True,
            register_hosts=register_hosts,
        )


def install_binary_from_release(
    url: str,
    binary_name: str,
    name_override: Optional[str] = None,
    register_hosts: bool = True,
    asset_pattern: Optional[str] = None,
) -> ImportResult:
    """
    Install a pre-built binary MCP server from GitHub Releases.

    Uses `gh release download` to fetch the binary.
    """
    owner, repo = _parse_github_url(url)
    name = name_override or repo

    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("gh (GitHub CLI) not found on PATH.")

    with tempfile.TemporaryDirectory() as tmp:
        dl_dir = Path(tmp) / "download"
        dl_dir.mkdir()

        cmd = [gh, "release", "download", "--repo", f"{owner}/{repo}", "--dir", str(dl_dir)]
        if asset_pattern:
            cmd += ["--pattern", asset_pattern]
        _run(cmd)

        downloaded = list(dl_dir.iterdir())
        if not downloaded:
            return ImportResult(
                success=False, skill_name=name, install_path=None,
                env_created=False, hosts_registered={},
                message="No assets downloaded from release.",
            )

        skill_dir = Path(tmp) / name
        skill_dir.mkdir()

        for f in downloaded:
            dest = skill_dir / f.name
            shutil.copy2(f, dest)
            if not dest.suffix or dest.suffix in (".bin", ""):
                dest.chmod(0o755)

        binary_path = skill_dir / binary_name
        if not binary_path.exists():
            for f in skill_dir.iterdir():
                if binary_name in f.name:
                    binary_path = f
                    binary_path.chmod(0o755)
                    break

        _generate_skill_toml(
            skill_dir, name, "binary", {},
            command=str(binary_path),
            args=[],
        )

        return import_from_dir(
            source_dir=skill_dir,
            rebuild_env=True,
            register_hosts=register_hosts,
        )
