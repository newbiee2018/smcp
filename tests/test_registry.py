"""Unit tests for the Registry."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tomli_w
from manager.models import SkillManifest
from manager.registry import Registry


SAMPLE = {
    "skill":   {"name": "reg-skill", "version": "0.1.0", "description": "test", "author": "x", "tags": []},
    "runtime": {"type": "python", "python_version": "3.10", "install_cmd": ""},
    "mcp":     {"entrypoint": "src/main.py", "transport": "stdio", "args": [], "env": {}},
    "hosts":   {"claude_code": True, "codex": False},
}


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.reg_path = Path(self.tmpdir.name) / "registry.toml"
        self.skill_dir = Path(self.tmpdir.name) / "reg-skill"
        self.skill_dir.mkdir()
        toml_path = self.skill_dir / "skill.toml"
        with open(toml_path, "wb") as f:
            tomli_w.dump(SAMPLE, f)
        self.manifest = SkillManifest.from_toml(toml_path)
        self.manifest.install_path = self.skill_dir

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_register_and_get(self):
        reg = Registry(self.reg_path)
        reg.register(self.manifest)
        result = reg.get("reg-skill")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "reg-skill")
        self.assertEqual(result.version, "0.1.0")

    def test_exists(self):
        reg = Registry(self.reg_path)
        self.assertFalse(reg.exists("reg-skill"))
        reg.register(self.manifest)
        self.assertTrue(reg.exists("reg-skill"))

    def test_unregister(self):
        reg = Registry(self.reg_path)
        reg.register(self.manifest)
        removed = reg.unregister("reg-skill")
        self.assertTrue(removed)
        self.assertFalse(reg.exists("reg-skill"))

    def test_list_all(self):
        reg = Registry(self.reg_path)
        reg.register(self.manifest)
        entries = reg.list_all()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "reg-skill")

    def test_mark_env_ready(self):
        reg = Registry(self.reg_path)
        reg.register(self.manifest)
        reg.mark_env_ready("reg-skill", True)
        entries = reg.list_all()
        self.assertTrue(entries[0]["env_ready"])

    def test_persistence(self):
        reg = Registry(self.reg_path)
        reg.register(self.manifest)
        # Create a fresh instance pointing to same file
        reg2 = Registry(self.reg_path)
        self.assertTrue(reg2.exists("reg-skill"))


if __name__ == "__main__":
    unittest.main()
