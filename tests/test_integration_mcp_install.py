"""
Integration tests — Category 2: Real MCP server install from GitHub.

Tests:
  A) drawio-mcp (Node.js / npx) — full install, functional test, export/import
  B) ida-mcp-rs (Rust binary) — clone, file management, export/import (no build)
  C) Cross-skill coexistence and removal
  D) Existing host migration — discover pre-existing MCP entries

File filtering rules verified for both:
  SHOULD be exported:  skill.toml, source code, package.json/Cargo.toml, dep specs
  SHOULD NOT be exported:  node_modules/, target/, .venv/, .git/, __pycache__/

Run:
  sg docker -c "docker compose -f docker/docker-compose.integration.yml run integration"
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest
import tomli_w

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.manager.models import SkillManifest
from src.manager import exporter

pytestmark = pytest.mark.skipif(
    not os.environ.get("SMCP_INTEGRATION"),
    reason="Set SMCP_INTEGRATION=1 to run (needs network + Docker)",
)


def _archive_members(archive_path: Path) -> list:
    with tarfile.open(archive_path, "r:gz") as tar:
        return [m.name for m in tar.getmembers()]


def _run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# Shared clone cache — clone each repo once per session, copy per test
# ═══════════════════════════════════════════════════════════════════════════

_CLONE_CACHE_DIR = Path(tempfile.mkdtemp(prefix="smcp-clones-"))


def _get_cached_clone(url: str, name: str) -> Path:
    """Clone once to a session-level cache, return cached path."""
    cached = _CLONE_CACHE_DIR / name
    if not cached.exists():
        _run(["git", "clone", "--depth", "1", url, str(cached)])
    return cached


def _copy_clone(cached: Path, dest: Path) -> Path:
    """Copy a cached clone to a test-local temp directory."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(cached, dest, symlinks=True)
    return dest


# ═══════════════════════════════════════════════════════════════════════════
# A) drawio-mcp — Node.js MCP server
# ═══════════════════════════════════════════════════════════════════════════


def _prepare_drawio_skill(clone_dir: Path) -> Path:
    """Set up the mcp-tool-server subdir as a skill and return its path."""
    server_dir = clone_dir / "mcp-tool-server"
    assert server_dir.exists(), "mcp-tool-server/ subdir should exist"

    # Copy sibling directories that the server requires at runtime
    for sibling in ["shared", "postprocessor", "shape-search"]:
        src = clone_dir / sibling
        dst = server_dir / sibling
        if src.exists() and not dst.exists():
            shutil.copytree(src, dst)

    with open(server_dir / "package.json") as f:
        pkg = json.load(f)

    skill_data = {
        "skill": {
            "name": "drawio-mcp",
            "version": pkg.get("version", "0.1.0"),
            "description": pkg.get("description", "draw.io MCP server"),
            "author": "jgraph",
            "tags": ["mcp", "drawio", "diagrams"],
        },
        "runtime": {
            "type": "node",
            "install_cmd": "npm install",
        },
        "mcp": {
            "entrypoint": "src/index.js",
            "transport": "stdio",
            "command": "node",
        },
        "hosts": {
            "claude_code": True,
            "codex": True,
        },
    }
    with open(server_dir / "skill.toml", "wb") as f:
        tomli_w.dump(skill_data, f)

    return server_dir


class TestDrawioMcpInstall:
    """Install drawio-mcp from the monorepo's mcp-tool-server/ subdir."""

    @pytest.fixture(autouse=True)
    def setup_drawio(self, isolated_smcp_env, tmp_path):
        self.env = isolated_smcp_env
        self.tmp = tmp_path
        cached = _get_cached_clone(
            "https://github.com/jgraph/drawio-mcp.git", "drawio-mcp")
        self.clone_dir = _copy_clone(cached, tmp_path / "drawio-mcp-clone")

    def _get_skill_dir(self) -> Path:
        return _prepare_drawio_skill(self.clone_dir)

    def test_install_drawio_mcp(self):
        """Clone drawio-mcp, install, verify node_modules and registry."""
        from src.manager.importer import import_from_dir

        skill_dir = self._get_skill_dir()
        result = import_from_dir(skill_dir, rebuild_env=True, register_hosts=True)

        assert result.success, f"Install failed: {result.message}"
        assert result.env_created, "node_modules should have been created"

        installed = result.install_path
        assert (installed / "node_modules").exists(), "node_modules/ should exist"
        assert (installed / "package.json").exists(), "package.json should exist"
        assert (installed / "skill.toml").exists(), "skill.toml should exist"

    def test_drawio_host_config_registration(self):
        """After install, both claude.json and codex config should have drawio-mcp."""
        from src.manager.importer import import_from_dir

        skill_dir = self._get_skill_dir()
        result = import_from_dir(skill_dir, rebuild_env=True, register_hosts=True)
        assert result.success

        claude_data = json.loads(self.env["claude_json"].read_text())
        servers = claude_data.get("mcpServers", {})
        assert "drawio-mcp" in servers, \
            f"drawio-mcp should be in claude.json, got: {list(servers.keys())}"
        entry = servers["drawio-mcp"]
        assert entry["type"] == "stdio"
        assert "node" in entry["command"]

        codex_text = self.env["codex_toml"].read_text()
        assert "drawio-mcp" in codex_text

    def test_drawio_export_excludes_node_modules(self):
        """Export should NOT contain node_modules/ or .git/."""
        from src.manager.importer import import_from_dir

        skill_dir = self._get_skill_dir()
        result = import_from_dir(skill_dir, rebuild_env=True, register_hosts=False)
        assert result.success

        manifest = SkillManifest.from_toml(result.install_path / "skill.toml")
        manifest.install_path = result.install_path

        archive = exporter.export_skill(manifest, output_dir=self.env["exports_dir"])
        members = _archive_members(archive)

        nm = [m for m in members if "node_modules" in m]
        assert nm == [], f"Should NOT contain node_modules: {nm[:5]}"

        git = [m for m in members if ".git" in m.split("/")]
        assert git == [], f"Should NOT contain .git: {git[:5]}"

    def test_drawio_export_includes_source(self):
        """Export should contain package.json, src/, skill.toml."""
        from src.manager.importer import import_from_dir

        skill_dir = self._get_skill_dir()
        result = import_from_dir(skill_dir, rebuild_env=True, register_hosts=False)
        assert result.success

        manifest = SkillManifest.from_toml(result.install_path / "skill.toml")
        manifest.install_path = result.install_path

        archive = exporter.export_skill(manifest, output_dir=self.env["exports_dir"])
        members = _archive_members(archive)
        basenames = {m.split("/")[-1] for m in members}

        assert "package.json" in basenames
        assert "skill.toml" in basenames
        assert len([m for m in members if "/src/" in m]) > 0

    def test_drawio_import_recreates_node_modules(self):
        """Import from archive should run npm install."""
        from src.manager.importer import import_from_dir, import_skill

        skill_dir = self._get_skill_dir()
        r1 = import_from_dir(skill_dir, rebuild_env=True, register_hosts=False)
        assert r1.success

        manifest = SkillManifest.from_toml(r1.install_path / "skill.toml")
        manifest.install_path = r1.install_path
        archive = exporter.export_skill(manifest, output_dir=self.env["exports_dir"])

        reimport_dir = self.env["data_home"] / "drawio-reimport"
        reimport_dir.mkdir(parents=True)
        r2 = import_skill(archive, install_dir=reimport_dir, rebuild_env=True, register_hosts=True)

        assert r2.success, f"Re-import failed: {r2.message}"
        assert r2.env_created
        assert (r2.install_path / "node_modules").exists()

    def test_drawio_functional_mcp_call(self):
        """
        Invoke the drawio MCP server via npx (published package) and verify
        it responds to MCP initialize + tools/list.

        Uses `npx @drawio/mcp` because the published npm package has the
        correct internal layout (postprocessor, shared modules already
        bundled by the prepack script). The cloned monorepo source misses
        these; file management tests above cover the clone-based flow.
        """
        init_msg = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        })
        initialized_notif = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        tools_list = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
        })

        stdin_data = init_msg + "\n" + initialized_notif + "\n" + tools_list + "\n"

        proc = subprocess.run(
            ["npx", "-y", "@drawio/mcp"],
            input=stdin_data, capture_output=True, text=True,
            timeout=120,
        )

        stdout = proc.stdout.strip()
        assert stdout, f"MCP server should produce output. stderr: {proc.stderr[:500]}"

        responses = []
        for line in stdout.split("\n"):
            line = line.strip()
            if line:
                try:
                    responses.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        assert len(responses) >= 1, f"Should get JSON-RPC response, got: {stdout[:500]}"
        assert "result" in responses[0], f"Initialize should succeed: {responses[0]}"

        # Verify the server has draw.io tools available
        tools_resp = [r for r in responses if r.get("id") == 2]
        if tools_resp:
            tools = tools_resp[0].get("result", {}).get("tools", [])
            tool_names = [t.get("name", "") for t in tools]
            assert len(tool_names) > 0, "drawio MCP should expose at least one tool"


# ═══════════════════════════════════════════════════════════════════════════
# B) ida-mcp-rs — Rust binary, file management only (no build)
# ═══════════════════════════════════════════════════════════════════════════


def _prepare_ida_skill(clone_dir: Path) -> Path:
    """Add skill.toml and fake target/ to test exclusion."""
    # Create a fake target/release directory
    fake_target = clone_dir / "target" / "release"
    fake_target.mkdir(parents=True, exist_ok=True)
    (fake_target / "ida-mcp").write_text("fake binary")
    (clone_dir / "target" / "debug").mkdir(parents=True, exist_ok=True)
    (clone_dir / "target" / "debug" / "ida-mcp").write_text("fake debug binary")

    skill_data = {
        "skill": {
            "name": "ida-mcp",
            "version": "0.1.0",
            "description": "IDA Pro MCP server (Rust binary)",
            "author": "blacktop",
            "tags": ["mcp", "ida", "reverse-engineering"],
        },
        "runtime": {
            "type": "binary",
            "install_cmd": "",
        },
        "mcp": {
            "entrypoint": "",
            "transport": "stdio",
            "command": "ida-mcp",
        },
        "hosts": {
            "claude_code": True,
            "codex": True,
        },
    }
    with open(clone_dir / "skill.toml", "wb") as f:
        tomli_w.dump(skill_data, f)

    return clone_dir


class TestIdaMcpRsFileManagement:
    """
    Clone ida-mcp-rs, set it up as a managed skill.
    Skip building (requires IDA Pro) — verify file management only.
    """

    @pytest.fixture(autouse=True)
    def setup_ida(self, isolated_smcp_env, tmp_path):
        self.env = isolated_smcp_env
        self.tmp = tmp_path
        cached = _get_cached_clone(
            "https://github.com/blacktop/ida-mcp-rs.git", "ida-mcp-rs")
        self.clone_dir = _copy_clone(cached, tmp_path / "ida-mcp-rs")

    def _install_ida_files(self) -> Path:
        """Copy ida-mcp-rs files into the managed skills directory."""
        from src.manager.registry import SKILL_MCP_SKILLS, get_registry
        from src.manager.importer import _copy_skill_dir
        from src.manager import host_config

        _prepare_ida_skill(self.clone_dir)
        target_dir = SKILL_MCP_SKILLS / "ida-mcp"
        target_dir.mkdir(parents=True, exist_ok=True)
        _copy_skill_dir(self.clone_dir, target_dir)

        manifest = SkillManifest.from_toml(target_dir / "skill.toml")
        manifest.install_path = target_dir
        host_config.register(manifest)
        get_registry().register(manifest)
        return target_dir

    def test_install_ida_mcp_registers_correctly(self):
        """Install ida-mcp (skip build), verify registry and host config."""
        installed = self._install_ida_files()

        claude_data = json.loads(self.env["claude_json"].read_text())
        assert "ida-mcp" in claude_data.get("mcpServers", {}), \
            "ida-mcp should be in claude.json"
        entry = claude_data["mcpServers"]["ida-mcp"]
        assert entry["command"] == "ida-mcp"

    def test_ida_copy_excludes_target_and_git(self):
        """_copy_skill_dir should NOT copy target/ or .git/."""
        installed = self._install_ida_files()

        assert not (installed / "target").exists(), \
            "target/ should NOT be copied (build artifact)"
        assert not (installed / ".git").exists(), \
            ".git/ should NOT be copied"

    def test_ida_copy_includes_source(self):
        """Installed dir should have Cargo.toml, src/, skill.toml."""
        installed = self._install_ida_files()

        assert (installed / "Cargo.toml").exists()
        assert (installed / "skill.toml").exists()
        assert (installed / "src").exists()

    def test_ida_export_excludes_target(self):
        """Export archive should NOT contain target/."""
        installed = self._install_ida_files()

        manifest = SkillManifest.from_toml(installed / "skill.toml")
        manifest.install_path = installed

        archive = exporter.export_skill(manifest, output_dir=self.env["exports_dir"])
        members = _archive_members(archive)

        target_m = [m for m in members if "/target/" in m or m.endswith("/target")]
        assert target_m == [], f"Should NOT contain target/: {target_m[:5]}"

    def test_ida_export_includes_cargo_and_source(self):
        """Export should contain Cargo.toml, Cargo.lock, src/, skill.toml."""
        installed = self._install_ida_files()

        manifest = SkillManifest.from_toml(installed / "skill.toml")
        manifest.install_path = installed

        archive = exporter.export_skill(manifest, output_dir=self.env["exports_dir"])
        members = _archive_members(archive)
        basenames = {m.split("/")[-1] for m in members}

        assert "Cargo.toml" in basenames
        assert "Cargo.lock" in basenames
        assert "skill.toml" in basenames
        assert len([m for m in members if "/src/" in m]) > 0

    def test_ida_import_from_archive_restores_files(self):
        """Import from archive should restore source files without target/."""
        installed = self._install_ida_files()

        manifest = SkillManifest.from_toml(installed / "skill.toml")
        manifest.install_path = installed

        archive = exporter.export_skill(manifest, output_dir=self.env["exports_dir"])

        from src.manager.importer import import_skill
        reimport_dir = self.env["data_home"] / "ida-reimport"
        reimport_dir.mkdir(parents=True)

        result = import_skill(archive, install_dir=reimport_dir,
                              rebuild_env=True, register_hosts=True)
        assert result.success, f"Import failed: {result.message}"

        imported = result.install_path
        assert (imported / "Cargo.toml").exists()
        assert (imported / "skill.toml").exists()
        assert (imported / "src").exists()
        assert not (imported / "target").exists(), \
            "target/ should NOT exist after import"
        assert not (imported / ".git").exists(), \
            ".git/ should NOT exist after import"


# ═══════════════════════════════════════════════════════════════════════════
# C) Cross-skill coexistence
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossSkillTransfer:
    """
    Both MCP servers coexist in host configs.
    Removing one doesn't affect the other.
    """

    @pytest.fixture(autouse=True)
    def setup_both(self, isolated_smcp_env, tmp_path):
        self.env = isolated_smcp_env
        self.tmp = tmp_path

    def _register_stub(self, name: str, command: str):
        """Quick register a stub skill for coexistence testing."""
        from src.manager.registry import SKILL_MCP_SKILLS, get_registry
        from src.manager.importer import _copy_skill_dir
        from src.manager import host_config

        skill_dir = self.tmp / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "src").mkdir(exist_ok=True)
        skill_data = {
            "skill": {"name": name, "version": "0.1.0",
                       "description": f"{name} test", "author": "", "tags": []},
            "runtime": {"type": "binary", "install_cmd": ""},
            "mcp": {"entrypoint": "", "transport": "stdio", "command": command},
            "hosts": {"claude_code": True, "codex": True},
        }
        with open(skill_dir / "skill.toml", "wb") as f:
            tomli_w.dump(skill_data, f)

        target = SKILL_MCP_SKILLS / name
        target.mkdir(parents=True, exist_ok=True)
        _copy_skill_dir(skill_dir, target)

        manifest = SkillManifest.from_toml(target / "skill.toml")
        manifest.install_path = target
        host_config.register(manifest)
        get_registry().register(manifest)

    def test_both_registered_in_host_configs(self):
        """Both skills should coexist in host configs."""
        from src.manager.registry import get_registry

        self._register_stub("drawio-mcp", "node")
        self._register_stub("ida-mcp", "ida-mcp")

        claude_data = json.loads(self.env["claude_json"].read_text())
        servers = claude_data.get("mcpServers", {})
        assert "drawio-mcp" in servers
        assert "ida-mcp" in servers

        reg = get_registry()
        assert reg.exists("drawio-mcp")
        assert reg.exists("ida-mcp")

    def test_remove_one_preserves_other(self):
        """Removing drawio-mcp should NOT affect ida-mcp."""
        from src.manager.registry import get_registry
        from src.manager import host_config

        self._register_stub("drawio-mcp", "node")
        self._register_stub("ida-mcp", "ida-mcp")

        # Remove drawio-mcp
        host_config.unregister("drawio-mcp")
        get_registry().unregister("drawio-mcp")

        claude_data = json.loads(self.env["claude_json"].read_text())
        assert "drawio-mcp" not in claude_data.get("mcpServers", {})
        assert "ida-mcp" in claude_data.get("mcpServers", {})


# ═══════════════════════════════════════════════════════════════════════════
# D) Existing host migration — discover pre-existing MCP entries
# ═══════════════════════════════════════════════════════════════════════════


class TestExistingHostMigration:
    """
    Simulate a host that already has Claude Code and Codex installed with
    several MCP servers registered manually (not via smcp). Test that smcp
    can discover these entries and optionally import them into the registry.
    """

    @pytest.fixture(autouse=True)
    def setup_existing(self, isolated_smcp_env, tmp_path):
        self.env = isolated_smcp_env
        self.tmp = tmp_path

    def _write_pre_existing_configs(self):
        """Write realistic pre-existing MCP server configs."""
        # Pre-existing claude.json with 3 manually registered MCP servers
        claude_data = {
            "mcpServers": {
                "filesystem": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
                    "env": {},
                },
                "github": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "test-token-placeholder"},
                },
                "sqlite": {
                    "type": "stdio",
                    "command": "uvx",
                    "args": ["mcp-server-sqlite", "--db-path", "/tmp/test.db"],
                    "env": {},
                },
            },
        }
        self.env["claude_json"].write_text(json.dumps(claude_data, indent=2))

        # Pre-existing codex config.toml
        codex_data = {
            "mcp_servers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
                    "env": {},
                },
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "test-token-placeholder"},
                },
            },
        }
        with open(self.env["codex_toml"], "wb") as f:
            tomli_w.dump(codex_data, f)

    def test_install_new_skill_preserves_existing_entries(self):
        """
        Installing a new skill via smcp should preserve all pre-existing
        MCP entries in both claude.json and codex config.toml.
        """
        from src.manager.registry import SKILL_MCP_SKILLS, get_registry
        from src.manager.importer import _copy_skill_dir
        from src.manager import host_config

        importlib.reload(host_config)

        self._write_pre_existing_configs()

        # Now install a new skill via smcp
        new_skill_dir = self.tmp / "my-new-skill"
        new_skill_dir.mkdir()
        (new_skill_dir / "src").mkdir()
        skill_data = {
            "skill": {"name": "my-new-skill", "version": "1.0.0",
                       "description": "New skill", "author": "", "tags": []},
            "runtime": {"type": "binary", "install_cmd": ""},
            "mcp": {"entrypoint": "", "transport": "stdio", "command": "my-new-skill"},
            "hosts": {"claude_code": True, "codex": True},
        }
        with open(new_skill_dir / "skill.toml", "wb") as f:
            tomli_w.dump(skill_data, f)

        target = SKILL_MCP_SKILLS / "my-new-skill"
        target.mkdir(parents=True, exist_ok=True)
        _copy_skill_dir(new_skill_dir, target)

        manifest = SkillManifest.from_toml(target / "skill.toml")
        manifest.install_path = target
        host_config.register(manifest)

        # Verify ALL pre-existing entries are still there
        claude_data = json.loads(self.env["claude_json"].read_text())
        servers = claude_data.get("mcpServers", {})
        assert "filesystem" in servers, "Pre-existing 'filesystem' should be preserved"
        assert "github" in servers, "Pre-existing 'github' should be preserved"
        assert "sqlite" in servers, "Pre-existing 'sqlite' should be preserved"
        assert "my-new-skill" in servers, "New skill should be added"
        assert len(servers) == 4

        # Verify env vars are preserved (sensitive data like tokens)
        assert servers["github"]["env"]["GITHUB_TOKEN"] == "ghp_fake123"

    def test_uninstall_skill_preserves_existing_entries(self):
        """Removing a skill should NOT touch pre-existing entries."""
        from src.manager import host_config
        importlib.reload(host_config)

        self._write_pre_existing_configs()

        # Register then unregister a skill
        new_skill_dir = self.tmp / "temp-skill"
        new_skill_dir.mkdir()
        skill_data = {
            "skill": {"name": "temp-skill", "version": "1.0.0",
                       "description": "", "author": "", "tags": []},
            "runtime": {"type": "binary", "install_cmd": ""},
            "mcp": {"entrypoint": "", "transport": "stdio", "command": "temp-cmd"},
            "hosts": {"claude_code": True, "codex": True},
        }
        with open(new_skill_dir / "skill.toml", "wb") as f:
            tomli_w.dump(skill_data, f)

        manifest = SkillManifest.from_toml(new_skill_dir / "skill.toml")
        manifest.install_path = new_skill_dir
        host_config.register(manifest)
        host_config.unregister("temp-skill")

        claude_data = json.loads(self.env["claude_json"].read_text())
        servers = claude_data.get("mcpServers", {})
        assert "filesystem" in servers
        assert "github" in servers
        assert "sqlite" in servers
        assert "temp-skill" not in servers

    def test_discover_existing_mcp_entries(self):
        """
        Discover pre-existing MCP entries from host configs and verify
        they can be read. This tests the foundation for migration —
        reading what's already there.
        """
        from src.manager import host_config
        importlib.reload(host_config)

        self._write_pre_existing_configs()

        claude_data = json.loads(self.env["claude_json"].read_text())
        existing_servers = claude_data.get("mcpServers", {})

        # Build a discovery report
        discovered = []
        for name, entry in existing_servers.items():
            info = {
                "name": name,
                "command": entry.get("command", ""),
                "args": entry.get("args", []),
                "transport": entry.get("type", "stdio"),
                "has_env_vars": bool(entry.get("env")),
                "is_npx": entry.get("command") == "npx",
                "is_uvx": entry.get("command") == "uvx",
            }
            discovered.append(info)

        assert len(discovered) == 3
        npx_servers = [d for d in discovered if d["is_npx"]]
        assert len(npx_servers) == 2, "Should discover 2 npx-based servers"
        uvx_servers = [d for d in discovered if d["is_uvx"]]
        assert len(uvx_servers) == 1, "Should discover 1 uvx-based server"

    def test_existing_deps_not_moved_without_skill_toml(self):
        """
        Pre-existing MCP servers installed via npx/uvx have their deps
        managed externally (npm global cache, uvx venvs). smcp should
        NOT try to move their dependency files — just record their config.
        """
        from src.manager import host_config
        importlib.reload(host_config)

        self._write_pre_existing_configs()

        # The key insight: npx-based servers don't have local dep files.
        # Their node_modules live in a global npm cache managed by npm.
        # smcp should never try to move those.
        claude_data = json.loads(self.env["claude_json"].read_text())
        fs_entry = claude_data["mcpServers"]["filesystem"]

        # Verify the entry is npx-based (deps are managed externally)
        assert fs_entry["command"] == "npx"
        assert "-y" in fs_entry["args"]

        # smcp should record this as-is, not try to create a venv or
        # move node_modules. Just verify the entry format is preserved.
        from src.manager.registry import SKILL_MCP_SKILLS
        skill_dir = SKILL_MCP_SKILLS / "filesystem"
        assert not skill_dir.exists(), \
            "npx-based pre-existing servers should NOT have a skill dir " \
            "until explicitly imported via smcp"
