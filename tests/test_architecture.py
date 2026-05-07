"""
Tests for architecture invariants discovered during development:
- runtime.type="none" (description-only skills)
- Native skill entries (SKILL.md) created on install, removed on uninstall
- CLI wrapper creation
- Per-skill venv isolation
- Existing host configs preserved during install/remove
- Builtin MCP servers never enter registry
- host_config skips MCP registration for runtime.type="none"
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tomli_w
from manager.models import SkillManifest, RuntimeConfig
from manager import host_config, importer, runtime as rt_mgr
from manager.registry import Registry, get_registry


def _write_toml(path: Path, data: dict) -> None:
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def _make_skill(base: Path, name: str, runtime_type: str = "python",
                extra_runtime: dict = None, extra_mcp: dict = None) -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "src").mkdir(exist_ok=True)
    data = {
        "skill": {
            "name": name,
            "version": "1.0.0",
            "description": f"Test skill: {name}",
            "author": "test",
            "tags": ["test"],
        },
        "runtime": {
            "type": runtime_type,
            "install_cmd": "",
            **(extra_runtime or {}),
        },
        "mcp": {
            "entrypoint": "src/main.py",
            "transport": "stdio",
            "args": [],
            "env": {},
            **(extra_mcp or {}),
        },
        "hosts": {"claude_code": True, "codex": True},
    }
    _write_toml(skill_dir / "skill.toml", data)
    if runtime_type == "python":
        (skill_dir / "requirements.txt").write_text("requests>=2.0.0\n")
    (skill_dir / "src" / "main.py").write_text("# stub\n")
    return skill_dir


class _IsolatedEnvMixin:
    """Sets up isolated env vars and reloads modules for each test."""

    def _setup_isolated_env(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

        self.data_home = self.tmp / "data"
        self.data_home.mkdir()
        self.config_home = self.tmp / "config"
        self.config_home.mkdir()

        self.claude_json = self.tmp / "claude.json"
        self.claude_json.write_text("{}")
        self.codex_dir = self.tmp / "codex"
        self.codex_dir.mkdir()
        self.codex_toml = self.codex_dir / "config.toml"
        self.codex_toml.write_text("")

        self.codex_home = self.tmp / "codex_home"
        self.codex_home.mkdir()
        self.claude_home = self.tmp / "claude_home"
        self.claude_home.mkdir()

        self._old_env = {}
        env_vars = {
            "XDG_DATA_HOME": str(self.data_home),
            "XDG_CONFIG_HOME": str(self.config_home),
            "CLAUDE_CONFIG_PATH": str(self.claude_json),
            "CODEX_CONFIG_PATH": str(self.codex_toml),
            "CODEX_HOME": str(self.codex_home),
            "HOME": str(self.claude_home),
        }
        for k, v in env_vars.items():
            self._old_env[k] = os.environ.get(k)
            os.environ[k] = v

        import manager.registry as reg_mod
        import manager.host_config as hc_mod
        reg_mod._registry = None
        importlib.reload(reg_mod)
        importlib.reload(hc_mod)

        global host_config, importer, rt_mgr
        host_config = hc_mod
        import manager.importer
        importlib.reload(manager.importer)
        importer = manager.importer

    def _teardown_isolated_env(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import manager.registry as reg_mod
        import manager.host_config as hc_mod
        reg_mod._registry = None
        importlib.reload(reg_mod)
        importlib.reload(hc_mod)

        global host_config, importer
        host_config = hc_mod
        import manager.importer
        importlib.reload(manager.importer)
        importer = manager.importer
        self.tmpdir.cleanup()


# ──────────────────────────────────────────────────────────────────────────── #
# runtime.type = "none"                                                        #
# ──────────────────────────────────────────────────────────────────────────── #

class TestRuntimeTypeNone(unittest.TestCase):
    def test_runtime_config_accepts_none(self):
        rc = RuntimeConfig(type="none", install_cmd="")
        self.assertEqual(rc.type, "none")

    def test_create_env_noop_for_none(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill(Path(d), "desc-only", runtime_type="none")
            m = SkillManifest.from_toml(skill_dir / "skill.toml")
            m.install_path = skill_dir
            rt_mgr.create_env(m)
            self.assertFalse((skill_dir / ".venv").exists())
            self.assertFalse((skill_dir / "node_modules").exists())

    def test_remove_env_noop_for_none(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill(Path(d), "desc-only", runtime_type="none")
            m = SkillManifest.from_toml(skill_dir / "skill.toml")
            m.install_path = skill_dir
            rt_mgr.remove_env(m)

    def test_env_status_none(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill(Path(d), "desc-only", runtime_type="none")
            m = SkillManifest.from_toml(skill_dir / "skill.toml")
            m.install_path = skill_dir
            status = rt_mgr.env_status(m)
            self.assertTrue(status["ready"])
            self.assertEqual(status["type"], "none")

    def test_from_toml_none_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill(Path(d), "desc-only", runtime_type="none")
            m = SkillManifest.from_toml(skill_dir / "skill.toml")
            self.assertEqual(m.runtime.type, "none")


class TestRuntimeTypeNoneHostConfig(_IsolatedEnvMixin, unittest.TestCase):
    def setUp(self):
        self._setup_isolated_env()

    def tearDown(self):
        self._teardown_isolated_env()

    def test_register_skips_mcp_for_none(self):
        skill_dir = _make_skill(self.tmp / "skills", "desc-only", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        result = host_config.register(m)
        self.assertTrue(result.get("claude_code"))
        self.assertTrue(result.get("codex"))
        data = json.loads(self.claude_json.read_text())
        self.assertNotIn("desc-only", data.get("mcpServers", {}))


# ──────────────────────────────────────────────────────────────────────────── #
# Native skill entries (SKILL.md)                                  #
# ──────────────────────────────────────────────────────────────────────────── #

class TestNativeSkillEntries(_IsolatedEnvMixin, unittest.TestCase):
    def setUp(self):
        self._setup_isolated_env()

    def tearDown(self):
        self._teardown_isolated_env()

    def test_post_install_generates_skill_md(self):
        skill_dir = _make_skill(self.tmp / "skills", "gen-test", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        codex_skill = self.codex_home / "skills" / "gen-test" / "SKILL.md"
        self.assertTrue(codex_skill.exists())
        content = codex_skill.read_text()
        self.assertIn("gen-test", content)
        self.assertIn("name:", content)

    def test_post_install_generates_claude_md(self):
        skill_dir = _make_skill(self.tmp / "skills", "gen-test", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        claude_skill = self.claude_home / ".claude" / "skills" / "gen-test" / "SKILL.md"
        self.assertTrue(claude_skill.exists())
        content = claude_skill.read_text()
        self.assertIn("gen-test", content)

    def test_post_install_copies_custom_skill_md(self):
        skill_dir = _make_skill(self.tmp / "skills", "custom-skill", runtime_type="none")
        custom_dir = skill_dir / "skills" / "codex"
        custom_dir.mkdir(parents=True)
        (custom_dir / "SKILL.md").write_text(
            "---\nname: custom-skill\ndescription: Custom skill\n---\nCustom content\n"
        )
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        installed = self.codex_home / "skills" / "custom-skill" / "SKILL.md"
        self.assertTrue(installed.exists())
        self.assertIn("Custom content", installed.read_text())

    def test_post_remove_cleans_native_dirs(self):
        skill_dir = _make_skill(self.tmp / "skills", "removable", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        codex_skill_dir = self.codex_home / "skills" / "removable"
        claude_skill_dir = self.claude_home / ".claude" / "skills" / "removable"
        self.assertTrue(codex_skill_dir.exists())
        self.assertTrue(claude_skill_dir.exists())
        importer.post_remove("removable")
        self.assertFalse(codex_skill_dir.exists())
        self.assertFalse(claude_skill_dir.exists())

    def test_post_remove_noop_if_not_exists(self):
        importer.post_remove("nonexistent-skill")

    def test_generated_skill_md_has_frontmatter(self):
        skill_dir = _make_skill(self.tmp / "skills", "fm-test", runtime_type="python")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        codex_skill = self.codex_home / "skills" / "fm-test" / "SKILL.md"
        content = codex_skill.read_text()
        self.assertTrue(content.startswith("---"))
        self.assertIn("description:", content)

    def test_generated_claude_md_includes_mcp_info(self):
        skill_dir = _make_skill(self.tmp / "skills", "mcp-test", runtime_type="python")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        claude_skill = self.claude_home / ".claude" / "skills" / "mcp-test" / "SKILL.md"
        content = claude_skill.read_text()
        self.assertIn("MCP Server", content)
        self.assertIn("stdio", content)

    def test_generated_none_skill_no_mcp_section(self):
        skill_dir = _make_skill(self.tmp / "skills", "no-mcp", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        codex_skill = self.codex_home / "skills" / "no-mcp" / "SKILL.md"
        content = codex_skill.read_text()
        self.assertNotIn("MCP Server", content)


# ──────────────────────────────────────────────────────────────────────────── #
# Skill discovery format (Claude Code & Codex require specific format)         #
# ──────────────────────────────────────────────────────────────────────────── #

class TestSkillDiscoveryFormat(_IsolatedEnvMixin, unittest.TestCase):
    """Verify installed skill files match host discovery requirements.

    Claude Code: ~/.claude/skills/<name>/SKILL.md with YAML frontmatter (name, description)
    Codex: ~/.codex/skills/<name>/SKILL.md with YAML frontmatter
    """

    def setUp(self):
        self._setup_isolated_env()

    def tearDown(self):
        self._teardown_isolated_env()

    def _parse_frontmatter(self, content):
        """Extract YAML frontmatter from markdown content."""
        if not content.startswith("---"):
            return None
        end = content.index("---", 3)
        fm_text = content[3:end].strip()
        result = {}
        for line in fm_text.split("\n"):
            if ":" in line and not line.startswith(" "):
                key, val = line.split(":", 1)
                result[key.strip()] = val.strip()
        return result

    def test_claude_skill_file_named_skill_md(self):
        """Claude Code requires SKILL.md, not CLAUDE.md."""
        skill_dir = _make_skill(self.tmp / "skills", "disc-test", runtime_type="python")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)

        skill_md = self.claude_home / ".claude" / "skills" / "disc-test" / "SKILL.md"
        claude_md = self.claude_home / ".claude" / "skills" / "disc-test" / "CLAUDE.md"
        self.assertTrue(skill_md.exists(), "SKILL.md must exist for Claude Code discovery")
        self.assertFalse(claude_md.exists(), "CLAUDE.md should not exist (wrong filename)")

    def test_claude_skill_has_required_frontmatter(self):
        """Claude Code needs frontmatter with name and description."""
        skill_dir = _make_skill(self.tmp / "skills", "fm-claude", runtime_type="python")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)

        content = (self.claude_home / ".claude" / "skills" / "fm-claude" / "SKILL.md").read_text()
        fm = self._parse_frontmatter(content)
        self.assertIsNotNone(fm, "SKILL.md must have YAML frontmatter")
        self.assertIn("name", fm, "frontmatter must have 'name'")
        self.assertIn("description", fm, "frontmatter must have 'description'")
        self.assertEqual(fm["name"], "fm-claude")

    def test_claude_skill_description_under_200_chars(self):
        """Claude Code truncates description at 200 chars."""
        skill_dir = _make_skill(self.tmp / "skills", "long-desc", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.description = "A" * 300
        m.install_path = skill_dir
        importer._post_install(m)

        content = (self.claude_home / ".claude" / "skills" / "long-desc" / "SKILL.md").read_text()
        fm = self._parse_frontmatter(content)
        self.assertLessEqual(len(fm["description"]), 200)

    def test_codex_skill_has_frontmatter(self):
        """Codex SKILL.md also needs frontmatter."""
        skill_dir = _make_skill(self.tmp / "skills", "fm-codex", runtime_type="python")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)

        content = (self.codex_home / "skills" / "fm-codex" / "SKILL.md").read_text()
        fm = self._parse_frontmatter(content)
        self.assertIsNotNone(fm, "Codex SKILL.md must have YAML frontmatter")
        self.assertIn("name", fm)
        self.assertIn("description", fm)

    def test_custom_claude_skill_md_preserved(self):
        """When skill ships skills/claude/SKILL.md, it is copied as-is."""
        skill_dir = _make_skill(self.tmp / "skills", "custom-claude", runtime_type="none")
        custom_dir = skill_dir / "skills" / "claude"
        custom_dir.mkdir(parents=True)
        custom_content = "---\nname: custom-claude\ndescription: Custom skill\n---\n\n# Custom\nHand-written instructions.\n"
        (custom_dir / "SKILL.md").write_text(custom_content)
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)

        installed = self.claude_home / ".claude" / "skills" / "custom-claude" / "SKILL.md"
        self.assertTrue(installed.exists())
        self.assertEqual(installed.read_text(), custom_content)

    def test_none_runtime_skill_discoverable(self):
        """Description-only skills (runtime=none) must also be discoverable."""
        skill_dir = _make_skill(self.tmp / "skills", "none-disc", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)

        for path in [
            self.claude_home / ".claude" / "skills" / "none-disc" / "SKILL.md",
            self.codex_home / "skills" / "none-disc" / "SKILL.md",
        ]:
            self.assertTrue(path.exists(), f"{path} must exist")
            content = path.read_text()
            self.assertTrue(content.startswith("---"), f"{path} must have frontmatter")

    def test_shipped_skill_md_has_valid_format(self):
        """The skill-mcp-protocol's own shipped SKILL.md files must be valid."""
        repo_root = Path(__file__).resolve().parent.parent
        for host in ["claude", "codex"]:
            with self.subTest(host=host):
                shipped = repo_root / "skills" / host / "SKILL.md"
                self.assertTrue(shipped.exists(), f"skills/{host}/SKILL.md must exist in repo")
                content = shipped.read_text()
                fm = self._parse_frontmatter(content)
                self.assertIsNotNone(fm, "shipped SKILL.md must have frontmatter")
                self.assertIn("name", fm)
                self.assertIn("description", fm)
                self.assertEqual(fm["name"], "skill-mcp-protocol")

    def test_no_claude_md_created_anywhere(self):
        """Ensure no CLAUDE.md is created in skill dirs (wrong filename)."""
        skill_dir = _make_skill(self.tmp / "skills", "no-wrong", runtime_type="python")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)

        claude_dir = self.claude_home / ".claude" / "skills" / "no-wrong"
        codex_dir = self.codex_home / "skills" / "no-wrong"
        for d in [claude_dir, codex_dir]:
            if d.exists():
                files = [f.name for f in d.iterdir()]
                self.assertNotIn("CLAUDE.md", files,
                                 f"CLAUDE.md should not exist in {d}")


# ──────────────────────────────────────────────────────────────────────────── #
# CLI wrapper creation                                                         #
# ──────────────────────────────────────────────────────────────────────────── #

class TestCLIWrapper(_IsolatedEnvMixin, unittest.TestCase):
    def setUp(self):
        self._setup_isolated_env()

    def tearDown(self):
        self._teardown_isolated_env()

    def test_cli_wrapper_created(self):
        skill_dir = _make_skill(self.tmp / "skills", "cli-test", runtime_type="python")
        (skill_dir / "src" / "cli.py").write_text("# cli stub\n")
        venv_bin = skill_dir / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\necho fake")
        (venv_bin / "python").chmod(0o755)
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        bin_dir = self.claude_home / ".local" / "bin"
        importer._post_install(m)
        wrapper = bin_dir / "clitest"
        self.assertTrue(wrapper.exists())
        content = wrapper.read_text()
        self.assertIn("exec", content)
        self.assertIn("cli.py", content)

    def test_smcp_wrapper_name_for_protocol(self):
        skill_dir = _make_skill(self.tmp / "skills", "skill-mcp-protocol", runtime_type="python")
        (skill_dir / "src" / "cli.py").write_text("# cli stub\n")
        venv_bin = skill_dir / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\necho fake")
        (venv_bin / "python").chmod(0o755)
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        smcp = self.claude_home / ".local" / "bin" / "smcp"
        self.assertTrue(smcp.exists())

    def test_no_cli_wrapper_without_cli_py(self):
        skill_dir = _make_skill(self.tmp / "skills", "no-cli", runtime_type="python")
        venv_bin = skill_dir / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\necho fake")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        bin_dir = self.claude_home / ".local" / "bin"
        self.assertFalse((bin_dir / "nocli").exists())

    def test_no_cli_wrapper_for_none_runtime(self):
        skill_dir = _make_skill(self.tmp / "skills", "no-cli-none", runtime_type="none")
        (skill_dir / "src" / "cli.py").write_text("# cli stub\n")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        importer._post_install(m)
        bin_dir = self.claude_home / ".local" / "bin"
        self.assertFalse((bin_dir / "noclinone").exists())


# ──────────────────────────────────────────────────────────────────────────── #
# Existing host config preservation                                            #
# ──────────────────────────────────────────────────────────────────────────── #

class TestHostConfigPreservation(_IsolatedEnvMixin, unittest.TestCase):
    def setUp(self):
        self._setup_isolated_env()

    def tearDown(self):
        self._teardown_isolated_env()

    def test_register_preserves_existing_claude_entries(self):
        self.claude_json.write_text(json.dumps({
            "mcpServers": {
                "existing-server": {"type": "stdio", "command": "node", "args": ["server.js"]}
            }
        }))
        skill_dir = _make_skill(self.tmp / "skills", "new-skill", runtime_type="none")
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        # none type skips MCP registration, but let's test with a python one
        skill_dir2 = _make_skill(self.tmp / "skills", "py-skill", runtime_type="python")
        venv_bin = skill_dir2 / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\necho fake")
        (venv_bin / "python").chmod(0o755)
        m2 = SkillManifest.from_toml(skill_dir2 / "skill.toml")
        m2.install_path = skill_dir2
        host_config.register(m2)
        data = json.loads(self.claude_json.read_text())
        self.assertIn("existing-server", data["mcpServers"])
        self.assertIn("py-skill", data["mcpServers"])

    def test_unregister_preserves_other_entries(self):
        self.claude_json.write_text(json.dumps({
            "mcpServers": {
                "keep-me": {"type": "stdio", "command": "node", "args": []},
                "remove-me": {"type": "stdio", "command": "python", "args": []},
            }
        }))
        host_config.unregister_claude("remove-me")
        data = json.loads(self.claude_json.read_text())
        self.assertIn("keep-me", data["mcpServers"])
        self.assertNotIn("remove-me", data["mcpServers"])

    def test_register_preserves_existing_codex_entries(self):
        import tomli_w as tw
        existing = {"mcp_servers": {"old-server": {"command": "npx", "args": ["-y", "old"]}}}
        with open(self.codex_toml, "wb") as f:
            tw.dump(existing, f)
        skill_dir = _make_skill(self.tmp / "skills", "new-codex", runtime_type="python")
        venv_bin = skill_dir / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\necho fake")
        (venv_bin / "python").chmod(0o755)
        m = SkillManifest.from_toml(skill_dir / "skill.toml")
        m.install_path = skill_dir
        host_config.register(m)
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
        with open(self.codex_toml, "rb") as f:
            data = tomllib.load(f)
        self.assertIn("old-server", data.get("mcp_servers", {}))
        self.assertIn("new-codex", data.get("mcp_servers", {}))


# ──────────────────────────────────────────────────────────────────────────── #
# Builtin MCP servers never enter registry                                     #
# ──────────────────────────────────────────────────────────────────────────── #

class TestRegistryIsolation(unittest.TestCase):
    def test_registry_starts_empty(self):
        with tempfile.TemporaryDirectory() as d:
            reg = Registry(Path(d) / "registry.toml")
            self.assertEqual(len(reg.list_all()), 0)

    def test_registry_only_contains_registered_skills(self):
        with tempfile.TemporaryDirectory() as d:
            reg = Registry(Path(d) / "registry.toml")
            skill_dir = _make_skill(Path(d), "my-skill", runtime_type="python")
            m = SkillManifest.from_toml(skill_dir / "skill.toml")
            m.install_path = skill_dir
            reg.register(m)
            entries = reg.list_all()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["name"], "my-skill")
            self.assertFalse(reg.exists("some-builtin-thing"))

    def test_unregister_removes_only_target(self):
        with tempfile.TemporaryDirectory() as d:
            reg = Registry(Path(d) / "registry.toml")
            for name in ["skill-a", "skill-b"]:
                sd = _make_skill(Path(d), name, runtime_type="python")
                m = SkillManifest.from_toml(sd / "skill.toml")
                m.install_path = sd
                reg.register(m)
            reg.unregister("skill-a")
            self.assertFalse(reg.exists("skill-a"))
            self.assertTrue(reg.exists("skill-b"))


# ──────────────────────────────────────────────────────────────────────────── #
# Per-skill venv isolation                                                     #
# ──────────────────────────────────────────────────────────────────────────── #

class TestPerSkillVenvIsolation(unittest.TestCase):
    def test_venv_paths_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            sd1 = _make_skill(Path(d), "skill-one", runtime_type="python")
            sd2 = _make_skill(Path(d), "skill-two", runtime_type="python")
            m1 = SkillManifest.from_toml(sd1 / "skill.toml")
            m2 = SkillManifest.from_toml(sd2 / "skill.toml")
            m1.install_path = sd1
            m2.install_path = sd2
            self.assertNotEqual(m1.venv_path, m2.venv_path)
            self.assertIn("skill-one", str(m1.venv_path))
            self.assertIn("skill-two", str(m2.venv_path))


# ──────────────────────────────────────────────────────────────────────────── #
# Import from dir full round-trip with native entries                          #
# ──────────────────────────────────────────────────────────────────────────── #

class TestImportFromDirNativeEntries(_IsolatedEnvMixin, unittest.TestCase):
    def setUp(self):
        self._setup_isolated_env()

    def tearDown(self):
        self._teardown_isolated_env()

    def test_import_none_skill_creates_native_entries(self):
        skill_dir = _make_skill(self.tmp / "source", "desc-skill", runtime_type="none")
        result = importer.import_from_dir(skill_dir, rebuild_env=False, register_hosts=True)
        self.assertTrue(result.success)
        codex_skill = self.codex_home / "skills" / "desc-skill" / "SKILL.md"
        claude_skill = self.claude_home / ".claude" / "skills" / "desc-skill" / "SKILL.md"
        self.assertTrue(codex_skill.exists())
        self.assertTrue(claude_skill.exists())

    def test_import_fails_when_native_skill_name_mismatches_manifest(self):
        skill_dir = _make_skill(self.tmp / "source", "frontmatter-mismatch", runtime_type="none")
        custom_dir = skill_dir / "skills" / "codex"
        custom_dir.mkdir(parents=True)
        (custom_dir / "SKILL.md").write_text(
            "---\nname: wrong-name\ndescription: Wrong name\n---\n\n# Wrong\n"
        )

        result = importer.import_from_dir(skill_dir, rebuild_env=False, register_hosts=True)

        self.assertFalse(result.success)
        self.assertIn("frontmatter name 'wrong-name'", result.message)
        self.assertIn("manifest name 'frontmatter-mismatch'", result.message)
        self.assertFalse(get_registry().exists("frontmatter-mismatch"))
        self.assertFalse(result.install_path.exists())
        self.assertFalse((self.codex_home / "skills" / "frontmatter-mismatch").exists())
        self.assertFalse(
            (self.claude_home / ".claude" / "skills" / "frontmatter-mismatch").exists()
        )


if __name__ == "__main__":
    unittest.main()
