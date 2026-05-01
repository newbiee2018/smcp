"""Unit tests for SkillManifest and related models (Python 3.8+ compatible)."""
import sys
import tempfile
import unittest
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tomli_w
from manager.models import SkillManifest, RuntimeConfig, McpConfig, HostsConfig


def _write_toml(path: Path, data: dict) -> None:
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


SAMPLE = {
    "skill": {
        "name": "test-skill",
        "version": "1.2.3",
        "description": "A test skill",
        "author": "tester",
        "tags": ["test", "demo"],
    },
    "runtime": {"type": "python", "python_version": "3.10", "install_cmd": "pip install -r requirements.txt"},
    "mcp":     {"entrypoint": "src/main.py", "transport": "stdio", "args": [], "env": {}},
    "hosts":   {"claude_code": True, "codex": True},
}


class TestSkillManifest(unittest.TestCase):
    def test_from_toml(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skill.toml"
            _write_toml(p, SAMPLE)
            m = SkillManifest.from_toml(p)
        self.assertEqual(m.name, "test-skill")
        self.assertEqual(m.version, "1.2.3")
        self.assertEqual(m.runtime.type, "python")
        self.assertEqual(m.runtime.python_version, "3.10")
        self.assertEqual(m.mcp.entrypoint, "src/main.py")
        self.assertTrue(m.hosts.claude_code)
        self.assertTrue(m.hosts.codex)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skill.toml"
            _write_toml(p, SAMPLE)
            m = SkillManifest.from_toml(p)
            m.install_path = Path(d)
            m.save()
            m2 = SkillManifest.from_toml(p)
        self.assertEqual(m.name, m2.name)
        self.assertEqual(m.version, m2.version)
        self.assertEqual(m.runtime.python_version, m2.runtime.python_version)

    def test_venv_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skill.toml"
            _write_toml(p, SAMPLE)
            m = SkillManifest.from_toml(p)
            m.install_path = Path(d)
            self.assertEqual(m.venv_path, Path(d) / ".venv")

    def test_env_not_ready_without_venv(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skill.toml"
            _write_toml(p, SAMPLE)
            m = SkillManifest.from_toml(p)
            m.install_path = Path(d)
            self.assertFalse(m.env_ready)

    def test_node_runtime(self):
        data = dict(SAMPLE)
        data["runtime"] = {"type": "node", "node_version": "18", "install_cmd": "npm install"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "skill.toml"
            _write_toml(p, data)
            m = SkillManifest.from_toml(p)
        self.assertEqual(m.runtime.type, "node")
        self.assertIsNone(m.runtime.python_version)


class TestRuntimeConfig(unittest.TestCase):
    def test_to_dict_python(self):
        rc = RuntimeConfig(type="python", python_version="3.10", install_cmd="pip install -r requirements.txt")
        d = rc.to_dict()
        self.assertEqual(d["type"], "python")
        self.assertEqual(d["python_version"], "3.10")

    def test_to_dict_omits_none(self):
        rc = RuntimeConfig(type="binary", install_cmd="")
        d = rc.to_dict()
        self.assertNotIn("python_version", d)
        self.assertNotIn("node_version", d)


if __name__ == "__main__":
    unittest.main()
