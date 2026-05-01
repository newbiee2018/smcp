"""Unit tests for skill export/import round-trip."""
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tomli_w
from manager.models import SkillManifest
from manager import exporter, importer

SAMPLE = {
    "skill":   {"name": "export-skill", "version": "2.0.0", "description": "export test", "author": "t", "tags": []},
    "runtime": {"type": "python", "python_version": "3.10", "install_cmd": "pip install -r requirements.txt"},
    "mcp":     {"entrypoint": "src/main.py", "transport": "stdio", "args": [], "env": {}},
    "hosts":   {"claude_code": True, "codex": True},
}


def _make_skill_dir(base: Path) -> Path:
    skill_dir = base / "export-skill"
    skill_dir.mkdir()
    (skill_dir / "src").mkdir()
    with open(skill_dir / "skill.toml", "wb") as f:
        tomli_w.dump(SAMPLE, f)
    (skill_dir / "requirements.txt").write_text("mcp>=1.0.0\n")
    (skill_dir / "src" / "main.py").write_text("# stub\n")
    return skill_dir


class TestExporter(unittest.TestCase):
    def test_creates_archive(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill_dir(Path(d))
            manifest = SkillManifest.from_toml(skill_dir / "skill.toml")
            manifest.install_path = skill_dir
            out_dir = Path(d) / "exports"
            out_dir.mkdir()
            archive = exporter.export_skill(manifest, out_dir)
            self.assertTrue(archive.exists())
            self.assertTrue(str(archive).endswith(".tar.gz"))

    def test_archive_contains_required_files(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill_dir(Path(d))
            manifest = SkillManifest.from_toml(skill_dir / "skill.toml")
            manifest.install_path = skill_dir
            out_dir = Path(d) / "exports"
            out_dir.mkdir()
            archive = exporter.export_skill(manifest, out_dir)
            with tarfile.open(archive, "r:gz") as tar:
                names = [m.name for m in tar.getmembers()]
            has = lambda suffix: any(n.endswith(suffix) for n in names)
            self.assertTrue(has("skill.toml"),       "skill.toml missing")
            self.assertTrue(has("SETUP.md"),         "SETUP.md missing")
            self.assertTrue(has("bootstrap.sh"),     "bootstrap.sh missing")
            self.assertTrue(has("agent-setup.json"), "agent-setup.json missing")

    def test_archive_excludes_venv(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill_dir(Path(d))
            # Create a fake .venv dir
            (skill_dir / ".venv" / "bin").mkdir(parents=True)
            (skill_dir / ".venv" / "bin" / "python").write_text("fake")
            manifest = SkillManifest.from_toml(skill_dir / "skill.toml")
            manifest.install_path = skill_dir
            out_dir = Path(d) / "exports"
            out_dir.mkdir()
            archive = exporter.export_skill(manifest, out_dir)
            with tarfile.open(archive, "r:gz") as tar:
                names = [m.name for m in tar.getmembers()]
            self.assertFalse(any(".venv" in n for n in names), ".venv should be excluded")

    def test_agent_setup_json_is_valid_json(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            skill_dir = _make_skill_dir(Path(d))
            manifest = SkillManifest.from_toml(skill_dir / "skill.toml")
            manifest.install_path = skill_dir
            out_dir = Path(d) / "exports"
            out_dir.mkdir()
            archive = exporter.export_skill(manifest, out_dir)
            with tarfile.open(archive, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("agent-setup.json"):
                        content = tar.extractfile(member).read().decode()
                        json.loads(content)  # raises if invalid
                        return
            self.fail("agent-setup.json not found in archive")


if __name__ == "__main__":
    unittest.main()
