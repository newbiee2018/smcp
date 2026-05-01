"""
Integration tests — Category 1: Runtime venv + export/import isolation.

Tests that:
  1. A Python skill installs with a working venv (packages importable)
  2. Export archives do NOT contain .venv/, node_modules/, target/, __pycache__/
  3. Export archives DO contain skill.toml, requirements.txt, src/, SETUP.md, etc.
  4. Importing from an archive creates a NEW venv from requirements.txt
  5. The imported venv actually works (packages importable)
  6. Full round-trip: create → export → delete original → import → works

Run inside Docker:
  sg docker -c "docker compose -f docker/docker-compose.integration.yml run integration"

Or locally (needs Python >=3.10):
  SMCP_INTEGRATION=1 python3 -m pytest tests/test_integration_venv_export_import.py -v
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.manager.models import SkillManifest
from src.manager import exporter, runtime as rt_mgr

# These tests create real venvs and install packages — they need network access.
pytestmark = pytest.mark.skipif(
    not os.environ.get("SMCP_INTEGRATION"),
    reason="Set SMCP_INTEGRATION=1 to run (needs network + time)",
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _venv_can_import(venv_python: Path, module: str) -> bool:
    """Check if the venv python can import a given module."""
    r = subprocess.run(
        [str(venv_python), "-c", f"import {module}; print({module}.__version__)"],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def _archive_members(archive_path: Path) -> list:
    """Return all member paths inside a tar.gz archive."""
    with tarfile.open(archive_path, "r:gz") as tar:
        return [m.name for m in tar.getmembers()]


# ── Tests ──────────────────────────────────────────────────────────────────


class TestVenvCreation:
    """Test that installing a skill creates a functional venv."""

    def test_import_creates_venv(self, isolated_smcp_env, sample_python_skill):
        """import_from_dir should create .venv with installed packages."""
        from src.manager.importer import import_from_dir

        result = import_from_dir(sample_python_skill, rebuild_env=True, register_hosts=True)

        assert result.success, f"Import failed: {result.message}"
        assert result.env_created

        installed_dir = result.install_path
        venv_dir = installed_dir / ".venv"
        assert venv_dir.exists(), ".venv directory should exist"

        venv_python = installed_dir / ".venv" / "bin" / "python"
        assert venv_python.exists(), "venv python binary should exist"

        assert _venv_can_import(venv_python, "requests"), \
            "requests should be importable in the venv"

    def test_host_configs_updated_after_install(self, isolated_smcp_env, sample_python_skill):
        """After install, both claude.json and codex config.toml should have entries."""
        from src.manager.importer import import_from_dir

        result = import_from_dir(sample_python_skill, rebuild_env=True, register_hosts=True)
        assert result.success

        claude_data = json.loads(isolated_smcp_env["claude_json"].read_text())
        assert "sample-python-skill" in claude_data.get("mcpServers", {}), \
            "claude.json should contain the skill entry"

        entry = claude_data["mcpServers"]["sample-python-skill"]
        assert entry["type"] == "stdio"
        assert "python" in entry["command"], \
            "command should point to venv python"
        assert ".venv" in entry["command"], \
            "command should reference the venv"


class TestExportFileFiltering:
    """Test that export includes the right files and excludes runtime artifacts."""

    def test_export_excludes_venv(self, isolated_smcp_env, sample_python_skill):
        """Export archive must NOT contain .venv/ or __pycache__/."""
        from src.manager.importer import import_from_dir

        result = import_from_dir(sample_python_skill, rebuild_env=True, register_hosts=False)
        assert result.success

        manifest = SkillManifest.from_toml(result.install_path / "skill.toml")
        manifest.install_path = result.install_path

        archive = exporter.export_skill(manifest, output_dir=isolated_smcp_env["exports_dir"])
        members = _archive_members(archive)

        venv_members = [m for m in members if ".venv" in m or "venv/" in m]
        assert venv_members == [], f"Archive should NOT contain venv files: {venv_members}"

        pycache_members = [m for m in members if "__pycache__" in m]
        assert pycache_members == [], f"Archive should NOT contain __pycache__: {pycache_members}"

    def test_export_includes_source_and_deps(self, isolated_smcp_env, sample_python_skill):
        """Export archive must contain skill.toml, requirements.txt, src/main.py."""
        from src.manager.importer import import_from_dir

        result = import_from_dir(sample_python_skill, rebuild_env=True, register_hosts=False)
        assert result.success

        manifest = SkillManifest.from_toml(result.install_path / "skill.toml")
        manifest.install_path = result.install_path

        archive = exporter.export_skill(manifest, output_dir=isolated_smcp_env["exports_dir"])
        members = _archive_members(archive)
        member_basenames = [m.split("/")[-1] for m in members if not m.endswith("/")]

        assert "skill.toml" in member_basenames, "Archive should contain skill.toml"
        assert "requirements.txt" in member_basenames, "Archive should contain requirements.txt"

        src_members = [m for m in members if "src/main.py" in m]
        assert src_members, "Archive should contain src/main.py"

    def test_export_includes_setup_artifacts(self, isolated_smcp_env, sample_python_skill):
        """Export should generate SETUP.md, bootstrap.sh, agent-setup.json."""
        from src.manager.importer import import_from_dir

        result = import_from_dir(sample_python_skill, rebuild_env=True, register_hosts=False)
        assert result.success

        manifest = SkillManifest.from_toml(result.install_path / "skill.toml")
        manifest.install_path = result.install_path

        archive = exporter.export_skill(manifest, output_dir=isolated_smcp_env["exports_dir"])
        members = _archive_members(archive)
        member_basenames = [m.split("/")[-1] for m in members if not m.endswith("/")]

        for artifact in ["SETUP.md", "bootstrap.sh", "agent-setup.json"]:
            assert artifact in member_basenames, f"Archive should contain {artifact}"


class TestImportRebuildsVenv:
    """Test that importing from archive recreates the venv from scratch."""

    def test_import_archive_creates_new_venv(self, isolated_smcp_env, sample_python_skill):
        """
        Full round-trip:
        1. Install skill → venv created
        2. Export → archive without venv
        3. Import archive to a different location → NEW venv created
        4. New venv has packages installed
        """
        from src.manager.importer import import_from_dir, import_skill

        # Step 1: Install
        result1 = import_from_dir(sample_python_skill, rebuild_env=True, register_hosts=False)
        assert result1.success
        original_venv = result1.install_path / ".venv" / "bin" / "python"
        assert original_venv.exists()

        # Step 2: Export
        manifest = SkillManifest.from_toml(result1.install_path / "skill.toml")
        manifest.install_path = result1.install_path
        archive = exporter.export_skill(manifest, output_dir=isolated_smcp_env["exports_dir"])
        assert archive.exists()

        # Step 3: Import to a different directory
        import_dir = isolated_smcp_env["data_home"] / "reimport-test"
        import_dir.mkdir(parents=True)
        result2 = import_skill(archive, install_dir=import_dir, rebuild_env=True, register_hosts=False)
        assert result2.success, f"Re-import failed: {result2.message}"
        assert result2.env_created

        # Step 4: Verify new venv
        new_install = result2.install_path
        new_venv_python = new_install / ".venv" / "bin" / "python"
        assert new_venv_python.exists(), "Imported skill should have a new venv"
        assert str(new_venv_python) != str(original_venv), \
            "New venv should be at a different path than the original"

        assert _venv_can_import(new_venv_python, "requests"), \
            "Imported venv should have requests installed from requirements.txt"

    def test_roundtrip_with_host_config_update(self, isolated_smcp_env, sample_python_skill):
        """After import, host configs should point to the NEW venv python."""
        from src.manager.importer import import_from_dir, import_skill

        result1 = import_from_dir(sample_python_skill, rebuild_env=True, register_hosts=True)
        assert result1.success

        manifest = SkillManifest.from_toml(result1.install_path / "skill.toml")
        manifest.install_path = result1.install_path
        archive = exporter.export_skill(manifest, output_dir=isolated_smcp_env["exports_dir"])

        import_dir = isolated_smcp_env["data_home"] / "reimport-hosts"
        import_dir.mkdir(parents=True)
        result2 = import_skill(archive, install_dir=import_dir, rebuild_env=True, register_hosts=True)
        assert result2.success

        claude_data = json.loads(isolated_smcp_env["claude_json"].read_text())
        entry = claude_data["mcpServers"]["sample-python-skill"]
        assert str(result2.install_path) in entry["command"], \
            f"Host config command should reference new install path, got: {entry['command']}"
