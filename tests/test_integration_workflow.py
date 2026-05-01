"""
Integration tests — AI agent workflow simulation.

Tests the full workflow that an AI agent (Codex/Claude Code) would follow:

A) CLI workflow: AI agent uses `smcp` CLI commands via shell
   - smcp install <path> → verify registration, native entries, venv
   - smcp list → verify skill appears
   - smcp export <name> → verify archive created
   - smcp import <archive> → verify round-trip
   - smcp remove <name> → verify cleanup

B) MCP server workflow: AI agent uses MCP tools via stdio
   - skill_install → same verification as CLI
   - skill_list, skill_info, skill_export, skill_import, skill_remove

C) Uninstallation: removing skill-mcp-protocol itself
   - smcp remove skill-mcp-protocol → native entries, CLI wrapper, registry cleaned

D) Self-install: skill-mcp-protocol installs itself on fresh host
   - smcp install . → verify CLI wrapper, native entries, NO MCP registration

Run:
  sg docker -c "docker compose -f docker/docker-compose.integration.yml run integration"

Or locally:
  SMCP_INTEGRATION=1 python3 -m pytest tests/test_integration_workflow.py -v
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import tomli_w

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("SMCP_INTEGRATION"),
    reason="Set SMCP_INTEGRATION=1 to run (needs network + venv creation)",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd, **kwargs):
    """Run a command, return CompletedProcess."""
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)


def _smcp(*args, env=None):
    """Run smcp CLI as a subprocess (simulates AI agent calling shell)."""
    cmd_env = os.environ.copy()
    if env:
        cmd_env.update(env)
    return _run(["smcp"] + list(args), env=cmd_env)


def _make_test_skill(base: Path, name: str, runtime_type: str = "python",
                     hosts_mcp: bool = True) -> Path:
    """Create a test skill directory."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "src").mkdir(exist_ok=True)

    data = {
        "skill": {
            "name": name,
            "version": "1.0.0",
            "description": f"Test skill: {name}",
            "author": "integration-test",
            "tags": ["test"],
        },
        "runtime": {"type": runtime_type, "install_cmd": ""},
        "mcp": {
            "entrypoint": "src/main.py",
            "transport": "stdio",
        },
        "hosts": {"claude_code": hosts_mcp, "codex": hosts_mcp},
    }

    if runtime_type == "python":
        data["runtime"]["install_cmd"] = "pip install -r requirements.txt"
        (skill_dir / "requirements.txt").write_text("requests>=2.0.0\n")

    with open(skill_dir / "skill.toml", "wb") as f:
        tomli_w.dump(data, f)

    (skill_dir / "src" / "main.py").write_text(
        '"""Stub MCP server for testing."""\nprint("hello")\n'
    )
    return skill_dir


# ═══════════════════════════════════════════════════════════════════════════
# A) CLI workflow — simulating what Codex/Claude Code would do via shell
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIWorkflow:
    """Full CLI workflow as an AI agent would execute it."""

    @pytest.fixture(autouse=True)
    def setup_env(self, isolated_smcp_env, tmp_path):
        self.env = isolated_smcp_env
        self.tmp = tmp_path
        self.cli_env = {
            "XDG_DATA_HOME": str(self.env["data_home"]),
            "CLAUDE_CONFIG_PATH": str(self.env["claude_json"]),
            "CODEX_CONFIG_PATH": str(self.env["codex_toml"]),
            "CODEX_HOME": str(self.tmp / "codex_home"),
            "HOME": str(self.tmp / "fakehome"),
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
        (self.tmp / "codex_home").mkdir(exist_ok=True)
        (self.tmp / "fakehome").mkdir(exist_ok=True)

    def test_cli_install_python_skill(self):
        """smcp install <dir> creates venv, registers, installs native entries."""
        skill_dir = _make_test_skill(self.tmp, "cli-test-skill", "python")

        result = _smcp("install", str(skill_dir), env=self.cli_env)
        output = json.loads(result.stdout.split("\n", 1)[-1])

        assert output["success"] is True
        assert output["env_created"] is True

        install_path = Path(output["install_path"])
        assert (install_path / ".venv" / "bin" / "python").exists()
        assert (install_path / "skill.toml").exists()

    def test_cli_list_shows_installed(self):
        """smcp list shows the installed skill."""
        skill_dir = _make_test_skill(self.tmp, "list-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        result = _smcp("list", env=self.cli_env)
        assert "list-test" in result.stdout

    def test_cli_info_shows_details(self):
        """smcp info <name> returns JSON with skill details."""
        skill_dir = _make_test_skill(self.tmp, "info-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        result = _smcp("info", "info-test", env=self.cli_env)
        data = json.loads(result.stdout)
        assert data["skill"]["name"] == "info-test"
        assert "env_status" in data

    def test_cli_export_creates_archive(self):
        """smcp export <name> creates a .skill.tar.gz archive."""
        skill_dir = _make_test_skill(self.tmp, "export-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        exports_dir = self.tmp / "exports"
        exports_dir.mkdir()
        result = _smcp("export", "export-test",
                        "--output-dir", str(exports_dir), env=self.cli_env)

        archives = list(exports_dir.glob("*.tar.gz"))
        assert len(archives) == 1
        assert "export-test" in archives[0].name

    def test_cli_import_from_archive(self):
        """smcp import <archive> installs from a .skill.tar.gz."""
        skill_dir = _make_test_skill(self.tmp, "imp-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        exports_dir = self.tmp / "exports"
        exports_dir.mkdir()
        _smcp("export", "imp-test",
              "--output-dir", str(exports_dir), env=self.cli_env)

        archive = list(exports_dir.glob("*.tar.gz"))[0]
        result = _smcp("import", str(archive), env=self.cli_env)
        assert "success" in result.stdout.lower() or "imp-test" in result.stdout

    def test_cli_remove_cleans_everything(self):
        """smcp remove <name> removes skill, env, host config, native entries."""
        skill_dir = _make_test_skill(self.tmp, "rm-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        # Verify it exists first
        result = _smcp("list", env=self.cli_env)
        assert "rm-test" in result.stdout

        # Remove it
        _smcp("remove", "rm-test", env=self.cli_env)

        # Verify it's gone
        result = _smcp("list", env=self.cli_env)
        assert "rm-test" not in result.stdout

        # Verify host configs are clean
        claude_data = json.loads(self.env["claude_json"].read_text())
        assert "rm-test" not in claude_data.get("mcpServers", {})

    def test_cli_install_none_runtime_skill(self):
        """smcp install a description-only skill (runtime.type=none)."""
        skill_dir = _make_test_skill(self.tmp, "desc-skill", "none", hosts_mcp=False)
        result = _smcp("install", str(skill_dir), env=self.cli_env)
        output = json.loads(result.stdout.split("\n", 1)[-1])

        assert output["success"] is True
        install_path = Path(output["install_path"])
        assert not (install_path / ".venv").exists()

        # Should NOT be in MCP host configs
        claude_data = json.loads(self.env["claude_json"].read_text())
        assert "desc-skill" not in claude_data.get("mcpServers", {})

    def test_cli_install_registers_host_configs(self):
        """smcp install registers the skill as MCP server in host configs."""
        skill_dir = _make_test_skill(self.tmp, "reg-test", "python", hosts_mcp=True)
        _smcp("install", str(skill_dir), env=self.cli_env)

        claude_data = json.loads(self.env["claude_json"].read_text())
        assert "reg-test" in claude_data.get("mcpServers", {}), \
            "Skill should be registered in claude.json"
        entry = claude_data["mcpServers"]["reg-test"]
        assert ".venv" in entry["command"], \
            "MCP entry should point to per-skill venv python"

    def test_cli_native_entries_created_on_install(self):
        """smcp install creates SKILL.md in native dirs."""
        skill_dir = _make_test_skill(self.tmp, "native-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        codex_home = self.tmp / "codex_home"
        fakehome = self.tmp / "fakehome"
        codex_skill = codex_home / "skills" / "native-test" / "SKILL.md"
        claude_skill = fakehome / ".claude" / "skills" / "native-test" / "SKILL.md"

        assert codex_skill.exists(), f"SKILL.md should exist at {codex_skill}"
        assert claude_skill.exists(), f"SKILL.md should exist at {claude_skill}"

    def test_cli_native_entries_removed_on_remove(self):
        """smcp remove also cleans native skill entries."""
        skill_dir = _make_test_skill(self.tmp, "clean-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        codex_home = self.tmp / "codex_home"
        fakehome = self.tmp / "fakehome"
        codex_skill_dir = codex_home / "skills" / "clean-test"
        claude_skill_dir = fakehome / ".claude" / "skills" / "clean-test"

        assert codex_skill_dir.exists()
        assert claude_skill_dir.exists()

        _smcp("remove", "clean-test", env=self.cli_env)

        assert not codex_skill_dir.exists(), "Native codex entry should be removed"
        assert not claude_skill_dir.exists(), "Native claude entry should be removed"

    def test_cli_installed_skill_discoverable_by_claude(self):
        """Installed skill must be discoverable: SKILL.md with frontmatter."""
        skill_dir = _make_test_skill(self.tmp, "discover-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        fakehome = self.tmp / "fakehome"
        skill_md = fakehome / ".claude" / "skills" / "discover-test" / "SKILL.md"
        assert skill_md.exists(), "SKILL.md must exist for Claude Code"

        content = skill_md.read_text()
        assert content.startswith("---"), "SKILL.md must have YAML frontmatter"
        assert "name:" in content, "frontmatter must contain name"
        assert "description:" in content, "frontmatter must contain description"
        assert "discover-test" in content

        # Must NOT have CLAUDE.md (wrong filename)
        claude_md = fakehome / ".claude" / "skills" / "discover-test" / "CLAUDE.md"
        assert not claude_md.exists(), "CLAUDE.md must not exist (wrong filename)"

    def test_cli_installed_skill_discoverable_by_codex(self):
        """Installed skill must be discoverable by Codex: SKILL.md with frontmatter."""
        skill_dir = _make_test_skill(self.tmp, "codex-disc", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        codex_home = self.tmp / "codex_home"
        skill_md = codex_home / "skills" / "codex-disc" / "SKILL.md"
        assert skill_md.exists(), "SKILL.md must exist for Codex"

        content = skill_md.read_text()
        assert content.startswith("---"), "SKILL.md must have YAML frontmatter"
        assert "name:" in content
        assert "description:" in content

    def test_cli_none_runtime_skill_discoverable(self):
        """Description-only skills must also produce discoverable SKILL.md."""
        skill_dir = _make_test_skill(self.tmp, "none-disc", "none", hosts_mcp=False)
        _smcp("install", str(skill_dir), env=self.cli_env)

        fakehome = self.tmp / "fakehome"
        codex_home = self.tmp / "codex_home"

        for path in [
            fakehome / ".claude" / "skills" / "none-disc" / "SKILL.md",
            codex_home / "skills" / "none-disc" / "SKILL.md",
        ]:
            assert path.exists(), f"{path} must exist"
            content = path.read_text()
            assert content.startswith("---"), f"{path} must have frontmatter"

    def test_cli_mcp_entry_valid_for_claude_mcp_list(self):
        """MCP entry in claude.json must have fields that 'claude mcp list' expects."""
        skill_dir = _make_test_skill(self.tmp, "mcp-valid", "python", hosts_mcp=True)
        _smcp("install", str(skill_dir), env=self.cli_env)

        claude_data = json.loads(self.env["claude_json"].read_text())
        entry = claude_data["mcpServers"]["mcp-valid"]
        assert "command" in entry, "MCP entry must have 'command'"
        assert "args" in entry, "MCP entry must have 'args'"
        assert isinstance(entry["args"], list)
        assert Path(entry["command"]).name == "python" or "python" in entry["command"], \
            "command should be the venv python"
        assert any("main.py" in a for a in entry["args"]), \
            "args should include the entrypoint"

    def test_cli_mcp_entry_valid_for_codex(self):
        """MCP entry in codex config.toml must be valid."""
        skill_dir = _make_test_skill(self.tmp, "codex-mcp", "python", hosts_mcp=True)
        _smcp("install", str(skill_dir), env=self.cli_env)

        codex_content = self.env["codex_toml"].read_text()
        assert "codex-mcp" in codex_content, \
            "Skill must appear in codex config"


# ═══════════════════════════════════════════════════════════════════════════
# B) MCP server workflow — tool calls via stdio protocol
# ═══════════════════════════════════════════════════════════════════════════

class TestMCPServerWorkflow:
    """Test MCP server tool calls — the opt-in alternative to CLI."""

    @pytest.fixture(autouse=True)
    def setup_env(self, isolated_smcp_env, tmp_path):
        self.env = isolated_smcp_env
        self.tmp = tmp_path
        self.mcp_env = {
            "XDG_DATA_HOME": str(self.env["data_home"]),
            "CLAUDE_CONFIG_PATH": str(self.env["claude_json"]),
            "CODEX_CONFIG_PATH": str(self.env["codex_toml"]),
            "CODEX_HOME": str(self.tmp / "codex_home"),
            "HOME": str(self.tmp / "fakehome"),
        }
        (self.tmp / "codex_home").mkdir(exist_ok=True)
        (self.tmp / "fakehome").mkdir(exist_ok=True)

    def _mcp_call(self, tool_name: str, arguments: dict) -> dict:
        """Send an MCP tool call via stdio and return the parsed result."""
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
        tool_msg = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })

        stdin_data = init_msg + "\n" + initialized_notif + "\n" + tool_msg + "\n"

        env = os.environ.copy()
        env.update(self.mcp_env)

        proc = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "src" / "main.py")],
            input=stdin_data, capture_output=True, text=True,
            timeout=120, env=env,
        )

        responses = []
        for line in proc.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    responses.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        tool_resp = [r for r in responses if r.get("id") == 2]
        assert tool_resp, f"No tool response. stderr: {proc.stderr[:500]}"

        content = tool_resp[0].get("result", {}).get("content", [])
        assert content, f"Empty content in tool response: {tool_resp[0]}"

        return json.loads(content[0]["text"])

    def test_mcp_skill_install(self):
        """MCP skill_install tool installs a skill."""
        skill_dir = _make_test_skill(self.tmp, "mcp-inst-test", "python")
        result = self._mcp_call("skill_install", {"source": str(skill_dir)})

        assert result["success"] is True
        assert result["env_created"] is True

    def test_mcp_skill_list(self):
        """MCP skill_list returns installed skills."""
        skill_dir = _make_test_skill(self.tmp, "mcp-list-test", "python")
        self._mcp_call("skill_install", {"source": str(skill_dir)})

        result = self._mcp_call("skill_list", {})
        assert result["count"] >= 1
        names = [s["name"] for s in result["skills"]]
        assert "mcp-list-test" in names

    def test_mcp_skill_info(self):
        """MCP skill_info returns details."""
        skill_dir = _make_test_skill(self.tmp, "mcp-info-test", "none", hosts_mcp=False)
        self._mcp_call("skill_install", {"source": str(skill_dir)})

        result = self._mcp_call("skill_info", {"name": "mcp-info-test"})
        assert result["skill"]["name"] == "mcp-info-test"

    def test_mcp_skill_remove(self):
        """MCP skill_remove uninstalls a skill."""
        skill_dir = _make_test_skill(self.tmp, "mcp-rm-test", "python")
        self._mcp_call("skill_install", {"source": str(skill_dir)})

        result = self._mcp_call("skill_remove", {"name": "mcp-rm-test"})
        assert result["removed"] == "mcp-rm-test"

        # Verify it's gone
        list_result = self._mcp_call("skill_list", {})
        names = [s["name"] for s in list_result["skills"]]
        assert "mcp-rm-test" not in names

    def test_mcp_protocol_info(self):
        """MCP protocol_info returns protocol description."""
        result = self._mcp_call("protocol_info", {})
        assert "skill-mcp-protocol" in result["name"]
        assert "available_tools" in result


# ═══════════════════════════════════════════════════════════════════════════
# C) Uninstallation — removing skill-mcp-protocol itself
# ═══════════════════════════════════════════════════════════════════════════

class TestSelfUninstall:
    """Test that skill-mcp-protocol can be cleanly removed from a host."""

    @pytest.fixture(autouse=True)
    def setup_env(self, isolated_smcp_env, tmp_path):
        self.env = isolated_smcp_env
        self.tmp = tmp_path
        self.cli_env = {
            "XDG_DATA_HOME": str(self.env["data_home"]),
            "CLAUDE_CONFIG_PATH": str(self.env["claude_json"]),
            "CODEX_CONFIG_PATH": str(self.env["codex_toml"]),
            "CODEX_HOME": str(self.tmp / "codex_home"),
            "HOME": str(self.tmp / "fakehome"),
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
        (self.tmp / "codex_home").mkdir(exist_ok=True)
        (self.tmp / "fakehome").mkdir(exist_ok=True)

    def _install_self(self):
        """Install skill-mcp-protocol from project source."""
        _smcp("install", str(PROJECT_ROOT), env=self.cli_env)

    def test_self_install_creates_expected_artifacts(self):
        """Installing skill-mcp-protocol creates venv, native entries, CLI wrapper."""
        self._install_self()

        result = _smcp("list", env=self.cli_env)
        assert "skill-mcp-protocol" in result.stdout

        codex_home = self.tmp / "codex_home"
        fakehome = self.tmp / "fakehome"
        assert (codex_home / "skills" / "skill-mcp-protocol" / "SKILL.md").exists()
        assert (fakehome / ".claude" / "skills" / "skill-mcp-protocol" / "SKILL.md").exists()

        # CLI wrapper (smcp)
        assert (fakehome / ".local" / "bin" / "smcp").exists()

    def test_self_install_no_mcp_registration(self):
        """skill-mcp-protocol should NOT register as MCP server (hosts=false)."""
        self._install_self()

        claude_data = json.loads(self.env["claude_json"].read_text())
        assert "skill-mcp-protocol" not in claude_data.get("mcpServers", {}), \
            "skill-mcp-protocol should NOT be in mcpServers"

    def test_self_remove_cleans_native_entries(self):
        """Removing skill-mcp-protocol cleans native skill dirs."""
        self._install_self()

        codex_home = self.tmp / "codex_home"
        fakehome = self.tmp / "fakehome"
        assert (codex_home / "skills" / "skill-mcp-protocol").exists()

        _smcp("remove", "skill-mcp-protocol", env=self.cli_env)

        assert not (codex_home / "skills" / "skill-mcp-protocol").exists()
        assert not (fakehome / ".claude" / "skills" / "skill-mcp-protocol").exists()

    def test_self_remove_cleans_registry(self):
        """Removing skill-mcp-protocol removes it from registry."""
        self._install_self()

        result = _smcp("list", env=self.cli_env)
        assert "skill-mcp-protocol" in result.stdout

        _smcp("remove", "skill-mcp-protocol", env=self.cli_env)

        result = _smcp("list", env=self.cli_env)
        assert "skill-mcp-protocol" not in result.stdout or "No skills" in result.stdout

    def test_remove_with_keep_files(self):
        """smcp remove --keep-files keeps source but removes env and registration."""
        skill_dir = _make_test_skill(self.tmp, "keep-files-test", "python")
        _smcp("install", str(skill_dir), env=self.cli_env)

        result = _smcp("info", "keep-files-test", env=self.cli_env)
        info = json.loads(result.stdout)
        install_path = Path(info["install_path"])
        assert (install_path / ".venv").exists()

        _smcp("remove", "keep-files-test", "--keep-files", env=self.cli_env)

        # Source files should still exist
        assert install_path.exists()
        assert (install_path / "skill.toml").exists()
        # But venv should be gone
        assert not (install_path / ".venv").exists()
        # And not in registry
        result = _smcp("list", env=self.cli_env)
        assert "keep-files-test" not in result.stdout

    def test_other_skills_survive_self_removal(self):
        """Removing skill-mcp-protocol should not affect other installed skills."""
        self._install_self()

        other = _make_test_skill(self.tmp, "survivor", "python")
        _smcp("install", str(other), env=self.cli_env)

        _smcp("remove", "skill-mcp-protocol", env=self.cli_env)

        result = _smcp("list", env=self.cli_env)
        assert "survivor" in result.stdout

        claude_data = json.loads(self.env["claude_json"].read_text())
        assert "survivor" in claude_data.get("mcpServers", {})
