"""
Runtime environment management (Python venvs, Node, binary).
Creates, rebuilds, and removes isolated environments per skill.
Environments are NEVER exported — they are rebuilt on the target host.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .models import SkillManifest


# ────────────────────────────────────────────────────────────────────────── #
# Helpers                                                                     #
# ────────────────────────────────────────────────────────────────────────────#

def _run(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def _python_bin(version: Optional[str]) -> str:
    """
    Try to locate a Python binary matching the requested version.
    Falls back to the current interpreter if no version is specified.
    """
    if not version:
        return sys.executable

    major, *rest = version.split(".")
    minor = rest[0] if rest else None

    candidates = []
    if minor:
        candidates.append(f"python{major}.{minor}")
    candidates += [f"python{major}", "python3", "python"]

    for name in candidates:
        path = shutil.which(name)
        if path:
            return path

    raise RuntimeError(
        f"Python {version} not found on PATH. "
        f"Please install it before importing this skill."
    )


def _node_bin() -> str:
    path = shutil.which("node")
    if not path:
        raise RuntimeError("Node.js not found on PATH.")
    return path


# ────────────────────────────────────────────────────────────────────────── #
# Public API                                                                  #
# ────────────────────────────────────────────────────────────────────────────#

def create_env(manifest: SkillManifest) -> None:
    """Create the isolated runtime environment for a skill."""
    rt = manifest.runtime
    skill_dir = manifest.install_path
    assert skill_dir, "Skill must have an install_path before creating env."

    if rt.type == "python":
        _create_python_venv(manifest)
    elif rt.type == "node":
        _install_node_deps(skill_dir)
    elif rt.type == "binary":
        _build_binary(manifest)
    else:
        raise ValueError(f"Unknown runtime type: {rt.type!r}")


def remove_env(manifest: SkillManifest) -> None:
    """Delete the runtime environment (safe to call even if it does not exist)."""
    rt = manifest.runtime
    skill_dir = manifest.install_path
    assert skill_dir

    if rt.type == "python":
        venv = skill_dir / ".venv"
        if venv.exists():
            shutil.rmtree(venv)
    elif rt.type == "node":
        nm = skill_dir / "node_modules"
        if nm.exists():
            shutil.rmtree(nm)
    elif rt.type == "binary":
        target = skill_dir / "target"
        if target.exists():
            shutil.rmtree(target)


def rebuild_env(manifest: SkillManifest) -> None:
    """Remove then recreate the runtime environment."""
    remove_env(manifest)
    create_env(manifest)


def env_status(manifest: SkillManifest) -> dict:
    """Return a dict describing the current env state."""
    rt = manifest.runtime
    skill_dir = manifest.install_path
    if not skill_dir:
        return {"ready": False, "reason": "no install_path"}

    if rt.type == "python":
        venv = skill_dir / ".venv"
        python = manifest.venv_python
        return {
            "ready": python is not None,
            "venv_path": str(venv),
            "python_path": str(python) if python else None,
        }
    elif rt.type == "node":
        nm = skill_dir / "node_modules"
        return {"ready": nm.exists(), "node_modules": str(nm)}
    else:
        return {"ready": True, "type": "binary"}


# ────────────────────────────────────────────────────────────────────────── #
# Internal                                                                    #
# ────────────────────────────────────────────────────────────────────────────#

def _create_python_venv(manifest: SkillManifest) -> None:
    skill_dir = manifest.install_path
    assert skill_dir
    python = _python_bin(manifest.runtime.python_version)
    venv_dir = skill_dir / ".venv"

    # Create the venv
    _run([python, "-m", "venv", str(venv_dir)])

    # Locate pip inside the venv
    pip = _venv_pip(venv_dir)

    # Upgrade pip silently
    _run([str(pip), "install", "--upgrade", "pip", "--quiet"])

    # Install deps via install_cmd or fall back to requirements.txt / pyproject.toml
    install_cmd = manifest.runtime.install_cmd
    if install_cmd:
        # Run as a shell command inside the venv env
        _run(
            [str(_venv_python(venv_dir)), "-m", "pip", "install"]
            + _parse_install_args(install_cmd),
            cwd=skill_dir,
        )
    elif (skill_dir / "requirements.txt").exists():
        _run(
            [str(pip), "install", "-r", "requirements.txt", "--quiet"],
            cwd=skill_dir,
        )
    elif (skill_dir / "pyproject.toml").exists():
        _run([str(pip), "install", ".", "--quiet"], cwd=skill_dir)


def _install_node_deps(skill_dir: Path) -> None:
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found on PATH.")
    _run([npm, "install"], cwd=skill_dir)


def _venv_python(venv_dir: Path) -> Path:
    for p in [venv_dir / "bin" / "python", venv_dir / "Scripts" / "python.exe"]:
        if p.exists():
            return p
    raise RuntimeError(f"Cannot find python in venv at {venv_dir}")


def _venv_pip(venv_dir: Path) -> Path:
    for p in [venv_dir / "bin" / "pip", venv_dir / "Scripts" / "pip.exe"]:
        if p.exists():
            return p
    raise RuntimeError(f"Cannot find pip in venv at {venv_dir}")


def _build_binary(manifest: SkillManifest) -> None:
    """Build a binary project (currently supports Rust/cargo)."""
    skill_dir = manifest.install_path
    assert skill_dir
    if (skill_dir / "Cargo.toml").exists():
        cargo = shutil.which("cargo")
        if not cargo:
            return
        _run([cargo, "build", "--release"], cwd=skill_dir)


def _parse_install_args(install_cmd: str) -> List[str]:
    """
    Extract trailing args from install_cmd.
    e.g. 'pip install -r requirements.txt' -> ['-r', 'requirements.txt']
    """
    parts = install_cmd.strip().split()
    # Drop 'pip' / 'pip3' / 'pip install' prefix
    while parts and parts[0] in ("pip", "pip3", "install"):
        parts.pop(0)
    return parts or ["-r", "requirements.txt"]
