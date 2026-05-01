"""Unit tests for host_config — Claude Code and Codex registration."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tomli_w
from manager.models import SkillManifest
from manager import host_config


SAMPLE = {
    "skill":   {"name": "cfg-skill", "version": "1.0.0", "description": "cfg test", "author": "t", "tags": []},
    "runtime": {"type": "python", "python_version": "3.10", "install_cmd": ""},
    "mcp":     {"entrypoint": "src/main.py", "transport": "stdio", "args": [], "env": {}},
    "hosts":   {"claude_code": True, "codex": True},
}


class TestHostConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.claude_cfg  = tmp / ".claude.json"
        self.codex_dir   = tmp / ".codex"
        self.codex_dir.mkdir()
        self.codex_cfg   = self.codex_dir / "config.toml"
        # Override paths via env vars
        os.environ["CLAUDE_CONFIG_PATH"] = str(self.claude_cfg)
        os.environ["CODEX_CONFIG_PATH"]  = str(self.codex_cfg)
        # Force module to reload config paths
        import importlib
        importlib.reload(host_config)

        skill_dir = tmp / "cfg-skill"
        skill_dir.mkdir()
        (skill_dir / "src").mkdir()
        toml_path = skill_dir / "skill.toml"
        with open(toml_path, "wb") as f:
            tomli_w.dump(SAMPLE, f)
        # Create fake venv python
        venv_bin = skill_dir / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\necho fake")
        self.manifest = SkillManifest.from_toml(toml_path)
        self.manifest.install_path = skill_dir

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("CLAUDE_CONFIG_PATH", None)
        os.environ.pop("CODEX_CONFIG_PATH",  None)

    def test_register_claude_creates_file(self):
        host_config.register_claude(self.manifest)
        self.assertTrue(self.claude_cfg.exists())
        data = json.loads(self.claude_cfg.read_text())
        self.assertIn("cfg-skill", data.get("mcpServers", {}))

    def test_register_claude_merges_existing(self):
        self.claude_cfg.write_text(json.dumps({"mcpServers": {"other": {"type": "stdio"}}}))
        host_config.register_claude(self.manifest)
        data = json.loads(self.claude_cfg.read_text())
        self.assertIn("other",     data["mcpServers"])
        self.assertIn("cfg-skill", data["mcpServers"])

    def test_unregister_claude(self):
        host_config.register_claude(self.manifest)
        removed = host_config.unregister_claude("cfg-skill")
        self.assertTrue(removed)
        data = json.loads(self.claude_cfg.read_text())
        self.assertNotIn("cfg-skill", data.get("mcpServers", {}))

    def test_register_codex_creates_entry(self):
        host_config.register_codex(self.manifest)
        self.assertTrue(self.codex_cfg.exists())
        content = self.codex_cfg.read_text()
        self.assertIn("cfg-skill", content)

    def test_is_registered_status(self):
        self.assertFalse(host_config.is_registered_claude("cfg-skill"))
        host_config.register_claude(self.manifest)
        self.assertTrue(host_config.is_registered_claude("cfg-skill"))


if __name__ == "__main__":
    unittest.main()
