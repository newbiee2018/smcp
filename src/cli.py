# SPDX-License-Identifier: MIT
"""
smcp — unified manager for AI skills and MCP servers.

Usage:
  smcp list
  smcp info <name>
  smcp install <path>
  smcp remove <name>
  smcp update <name> [--source <path>]
  smcp export <name> [--output-dir <dir>]
  smcp import <package.skill.tar.gz>
  smcp create <name> --description "..." [--runtime python|node|binary] [--author "..."]
  smcp register <name> [--hosts claude_code codex]
  smcp unregister <name> [--hosts claude_code codex]
  smcp rebuild-env <name>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

sys.path.insert(0, str(Path(__file__).parent))
from manager import exporter, host_config, importer, runtime as rt_mgr
from manager.registry import SKILL_MCP_SKILLS, SKILL_MCP_EXPORTS, get_registry


def _ok(data: dict) -> None:
    click.echo(json.dumps(data, indent=2))


def _err(msg: str) -> None:
    click.echo(click.style(f"✗ {msg}", fg="red"), err=True)
    sys.exit(1)


# ────────────────────────────────────────────────────────────────────────── #
# Root                                                                        #
# ────────────────────────────────────────────────────────────────────────────#

@click.group()
def cli():
    """smcp: unified manager for AI skills and MCP servers."""


# ── list ─────────────────────────────────────────────────────────────────────

@cli.command("list")
def cmd_list():
    """List all installed skills and MCP servers."""
    reg = get_registry()
    skills = reg.list_all()
    if not skills:
        click.echo("No skills or MCP servers installed.")
        return
    for s in skills:
        env = click.style("✓", fg="green") if s["env_ready"] else click.style("✗", fg="red")
        hosts = s.get("hosts", {})
        is_mcp = s["runtime_type"] != "none" and (hosts.get("claude_code") or hosts.get("codex"))
        kind = "mcp" if is_mcp else "skill"
        click.echo(f"  {env}  {s['name']:30s}  v{s['version']:10s}  {kind:5s}  {s['runtime_type']}")


# ── info ─────────────────────────────────────────────────────────────────────

@cli.command("info")
@click.argument("name")
def cmd_info(name: str):
    """Show details about an installed skill or MCP server."""
    reg = get_registry()
    manifest = reg.get(name)
    if not manifest:
        _err(f"Skill '{name}' not found.")
    env_status = rt_mgr.env_status(manifest)
    host_status = host_config.registration_status(name)
    _ok({**manifest.to_dict(), "install_path": str(manifest.install_path),
         "env_status": env_status, "host_status": host_status})


# ── install ───────────────────────────────────────────────────────────────────

@cli.command("install")
@click.argument("source")
@click.option("--no-rebuild-env", is_flag=True, default=False)
@click.option("--no-register",    is_flag=True, default=False)
def cmd_install(source: str, no_rebuild_env: bool, no_register: bool):
    """Install a skill or MCP server from a local directory or .skill.tar.gz."""
    src = Path(source).expanduser().resolve()
    if str(src).endswith(".tar.gz"):
        result = importer.import_skill(
            src,
            rebuild_env=not no_rebuild_env,
            register_hosts=not no_register,
        )
    else:
        result = importer.import_from_dir(
            src,
            rebuild_env=not no_rebuild_env,
            register_hosts=not no_register,
        )
    if result.success:
        click.echo(click.style(f"✓ {result.message}", fg="green"))
        _ok(result.to_dict())
    else:
        _err(result.message)


# ── remove ────────────────────────────────────────────────────────────────────

@cli.command("remove")
@click.argument("name")
@click.option("--keep-files", is_flag=True, default=False,
              help="Keep source files; only remove env and unregister.")
def cmd_remove(name: str, keep_files: bool):
    """Remove an installed skill or MCP server."""
    import shutil
    reg = get_registry()
    manifest = reg.get(name)
    if not manifest:
        _err(f"Skill '{name}' not found.")

    host_config.unregister(name)
    rt_mgr.remove_env(manifest)
    importer.post_remove(name)
    if not keep_files and manifest.install_path:
        shutil.rmtree(manifest.install_path, ignore_errors=True)
    reg.unregister(name)
    click.echo(click.style(f"✓ Skill '{name}' removed.", fg="green"))


# ── update ────────────────────────────────────────────────────────────────────

@cli.command("update")
@click.argument("name")
@click.option("--source", default=None, help="New source path or archive.")
def cmd_update(name: str, source: Optional[str] = None):
    """Update (or rebuild) an installed skill or MCP server."""
    reg = get_registry()
    if source:
        src = Path(source).expanduser().resolve()
        result = (
            importer.import_skill(src)
            if str(src).endswith(".tar.gz")
            else importer.import_from_dir(src)
        )
        click.echo(click.style(f"✓ {result.message}", fg="green"))
        return
    manifest = reg.get(name)
    if not manifest:
        _err(f"Skill '{name}' not found.")
    rt_mgr.rebuild_env(manifest)
    reg.mark_env_ready(name, manifest.env_ready)
    click.echo(click.style(f"✓ Skill '{name}' env rebuilt.", fg="green"))


# ── export ────────────────────────────────────────────────────────────────────

@cli.command("export")
@click.argument("name")
@click.option("--output-dir", default=None, help=f"Default: {SKILL_MCP_EXPORTS}")
def cmd_export(name: str, output_dir: Optional[str]):
    """Export a skill or MCP server to a portable .skill.tar.gz archive."""
    reg = get_registry()
    manifest = reg.get(name)
    if not manifest:
        _err(f"Skill '{name}' not found.")
    out = Path(output_dir) if output_dir else None
    archive = exporter.export_skill(manifest, out)
    click.echo(click.style(f"✓ Exported: {archive}", fg="green"))


# ── import ────────────────────────────────────────────────────────────────────

@cli.command("import")
@click.argument("package_path")
@click.option("--install-dir", default=None)
@click.option("--no-rebuild-env", is_flag=True, default=False)
@click.option("--no-register",    is_flag=True, default=False)
def cmd_import(package_path: str, install_dir: Optional[str],
               no_rebuild_env: bool, no_register: bool):
    """Import a skill or MCP server from a .skill.tar.gz archive."""
    result = importer.import_skill(
        Path(package_path).expanduser().resolve(),
        install_dir=Path(install_dir) if install_dir else None,
        rebuild_env=not no_rebuild_env,
        register_hosts=not no_register,
    )
    if result.success:
        click.echo(click.style(f"✓ {result.message}", fg="green"))
        _ok(result.to_dict())
    else:
        _err(result.message)


# ── create ────────────────────────────────────────────────────────────────────

@cli.command("create")
@click.argument("name")
@click.option("--description", required=True)
@click.option("--runtime", default="python",
              type=click.Choice(["python", "node", "binary", "none"]))
@click.option("--author", default="")
def cmd_create(name: str, description: str, runtime: str, author: str):
    """Scaffold a new skill or MCP server directory."""
    from jinja2 import Environment, FileSystemLoader
    import json as _json

    templates = Path(__file__).parent / "manager" / "templates"
    j2 = Environment(loader=FileSystemLoader(str(templates)), keep_trailing_newline=True)

    skill_dir = SKILL_MCP_SKILLS / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "src").mkdir(exist_ok=True)

    toml = j2.get_template("skill.toml.j2").render(
        name=name, description=description, runtime=runtime, author=author
    )
    (skill_dir / "skill.toml").write_text(toml)

    if runtime == "python":
        (skill_dir / "requirements.txt").write_text("mcp>=1.0.0\n")
        (skill_dir / "src" / "main.py").write_text(
            f'"""Implement your MCP server here."""\n# TODO\n'
        )
    elif runtime == "node":
        pkg = {"name": name, "version": "0.1.0",
               "dependencies": {"@modelcontextprotocol/sdk": "latest"}}
        (skill_dir / "package.json").write_text(_json.dumps(pkg, indent=2))
        (skill_dir / "src" / "main.js").write_text("// TODO: implement MCP server\n")

    click.echo(click.style(f"✓ Skill '{name}' scaffolded at {skill_dir}", fg="green"))
    click.echo(f"  Next: edit {skill_dir}/src/ then run: smcp install {skill_dir}")


# ── register / unregister ─────────────────────────────────────────────────────

@cli.command("register")
@click.argument("name")
@click.option("--hosts", multiple=True,
              type=click.Choice(["claude_code", "codex"]))
def cmd_register(name: str, hosts):
    """Register a skill or MCP server with host configs."""
    reg = get_registry()
    manifest = reg.get(name)
    if not manifest:
        _err(f"Skill '{name}' not found.")
    result = host_config.register(manifest, list(hosts) or None)
    click.echo(click.style(f"✓ Registered '{name}'", fg="green"))
    _ok(result)


@cli.command("unregister")
@click.argument("name")
@click.option("--hosts", multiple=True,
              type=click.Choice(["claude_code", "codex"]))
def cmd_unregister(name: str, hosts):
    """Remove a skill or MCP server from host configs (keeps files)."""
    result = host_config.unregister(name, list(hosts) or None)
    click.echo(click.style(f"✓ Unregistered '{name}'", fg="green"))
    _ok(result)


# ── rebuild-env ───────────────────────────────────────────────────────────────

@cli.command("rebuild-env")
@click.argument("name")
def cmd_rebuild_env(name: str):
    """Destroy and recreate the runtime environment for a skill or MCP server."""
    reg = get_registry()
    manifest = reg.get(name)
    if not manifest:
        _err(f"Skill '{name}' not found.")
    rt_mgr.rebuild_env(manifest)
    reg.mark_env_ready(name, manifest.env_ready)
    click.echo(click.style(f"✓ Env rebuilt for '{name}'.", fg="green"))



if __name__ == "__main__":
    cli()
