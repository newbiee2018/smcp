"""
Exporter — packages a skill into a portable .skill.tar.gz archive.

What IS included:
  - skill.toml
  - src/           (all source code)
  - requirements.txt / package.json / pyproject.toml  (dep specs)
  - SETUP.md       (human-readable setup guide)
  - bootstrap.sh   (automated setup script)
  - agent-setup.json  (machine-readable setup for AI agents)

What is NOT included (always gitignored, rebuilt on import):
  - .venv/
  - node_modules/
  - __pycache__/
  - *.pyc / *.pyo
"""
from __future__ import annotations

import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from .models import SkillManifest
from .registry import SKILL_MCP_EXPORTS

# Files/dirs that are NEVER exported
_EXCLUDE = {
    ".venv", "venv", "env",
    "node_modules",
    "__pycache__",
    ".git",
    "exports",
}
_EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".egg-info"}

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _should_include(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & _EXCLUDE:
        return False
    if rel.suffix in _EXCLUDE_SUFFIXES:
        return False
    return True


def _render(template_name: str, **ctx) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    return env.get_template(template_name).render(**ctx)


def export_skill(
    manifest: SkillManifest,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Export a skill to a .skill.tar.gz archive.

    Returns the path to the generated archive.
    """
    assert manifest.install_path, "Skill must have an install_path."
    skill_dir = manifest.install_path

    out_dir = output_dir or SKILL_MCP_EXPORTS
    out_dir.mkdir(parents=True, exist_ok=True)

    archive_name = f"{manifest.name}-{manifest.version}.skill.tar.gz"
    archive_path = out_dir / archive_name

    export_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ctx = {"manifest": manifest, "export_date": export_date}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / f"{manifest.name}-{manifest.version}"
        tmp_path.mkdir()

        # ── 1. Copy skill source files ──────────────────────────────────
        for src_file in skill_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(skill_dir)
            if not _should_include(rel):
                continue
            dest = tmp_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src_file.read_bytes())

        # ── 2. Generate setup artefacts ─────────────────────────────────
        (tmp_path / "SETUP.md").write_text(
            _render("SETUP.md.j2", **ctx), encoding="utf-8"
        )

        bootstrap = _render("bootstrap.sh.j2", **ctx)
        bs_path = tmp_path / "bootstrap.sh"
        bs_path.write_text(bootstrap, encoding="utf-8")
        bs_path.chmod(0o755)

        agent_setup = _render("agent-setup.json.j2", **ctx)
        # Validate JSON (catch template errors early)
        try:
            json.loads(agent_setup)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"agent-setup.json template produced invalid JSON: {e}"
            ) from e
        (tmp_path / "agent-setup.json").write_text(agent_setup, encoding="utf-8")

        # ── 3. Pack into tar.gz ─────────────────────────────────────────
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(tmp_path, arcname=f"{manifest.name}-{manifest.version}")

    return archive_path
