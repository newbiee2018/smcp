"""
skill-mcp-protocol — MCP server entry point.

Exposes tools that let any AI agent (Claude Code, Codex, …) manage skills:
  skill_list          list all installed skills
  skill_info          get details about one skill
  skill_install       install a skill from a local dir or .skill.tar.gz
  skill_remove        uninstall a skill
  skill_update        reinstall / rebuild an installed skill
  skill_export        package a skill into a portable .skill.tar.gz
  skill_import        import a .skill.tar.gz on this host
  skill_create        scaffold a new skill from template
  skill_register      (re)register a skill with Claude Code / Codex
  skill_unregister    remove a skill from host configs
  skill_rebuild_env   recreate the runtime environment for a skill
  protocol_info       describe this protocol to the AI agent

The protocol itself is a skill — bootstrapping instructions are in
agent-setup.json at the repo root.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Manager modules
sys.path.insert(0, str(Path(__file__).parent))
from manager import exporter, host_config, importer, runtime as rt_mgr
from manager.models import SkillManifest
from manager.registry import (
    SKILL_MCP_DATA,
    SKILL_MCP_EXPORTS,
    SKILL_MCP_SKILLS,
    get_registry,
)

# ── Jinja2 for skill scaffolding ────────────────────────────────────────────
from jinja2 import Environment, FileSystemLoader as _FL

_TEMPLATES = Path(__file__).parent / "manager" / "templates"
_j2 = Environment(loader=_FL(str(_TEMPLATES)), keep_trailing_newline=True)

# ────────────────────────────────────────────────────────────────────────── #
# Server                                                                      #
# ────────────────────────────────────────────────────────────────────────────#

server = Server("skill-mcp-protocol")


# ── Tool definitions ────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> List[types.Tool]:
    return [
        types.Tool(
            name="skill_list",
            description="List all skills installed on this host.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="skill_info",
            description="Get detailed information about an installed skill.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"}
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="skill_install",
            description=(
                "Install a skill from a local directory or .skill.tar.gz archive. "
                "Copies files to the global skills directory, creates the runtime "
                "environment, and registers with Claude Code / Codex."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Absolute path to a skill directory or .skill.tar.gz archive.",
                    },
                    "rebuild_env": {
                        "type": "boolean",
                        "default": True,
                        "description": "Destroy and recreate venv if it already exists.",
                    },
                    "register_hosts": {
                        "type": "boolean",
                        "default": True,
                        "description": "Auto-register with Claude Code and Codex.",
                    },
                },
                "required": ["source"],
            },
        ),
        types.Tool(
            name="skill_remove",
            description="Uninstall a skill: remove files, env, and host registrations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "keep_files": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, keep source files but remove env and unregister.",
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="skill_update",
            description=(
                "Update an installed skill: pull latest source from its original location "
                "and rebuild the runtime env. Provide source to update from a new path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "source": {
                        "type": "string",
                        "description": "Optional new source path; omit to rebuild in-place.",
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="skill_export",
            description=(
                "Package an installed skill into a portable .skill.tar.gz archive. "
                "The archive includes source, skill.toml, SETUP.md, bootstrap.sh, "
                "and agent-setup.json. Runtime environments (.venv, node_modules) "
                "are excluded — they are rebuilt on import."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "output_dir": {
                        "type": "string",
                        "description": f"Output directory (default: {SKILL_MCP_EXPORTS})",
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="skill_import",
            description=(
                "Import a .skill.tar.gz archive: extract, create runtime env, "
                "and register with host configs. Equivalent to running bootstrap.sh "
                "programmatically."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "package_path": {
                        "type": "string",
                        "description": "Path to the .skill.tar.gz file.",
                    },
                    "install_dir": {
                        "type": "string",
                        "description": f"Override install directory (default: {SKILL_MCP_SKILLS}/<name>)",
                    },
                    "rebuild_env":     {"type": "boolean", "default": True},
                    "register_hosts":  {"type": "boolean", "default": True},
                },
                "required": ["package_path"],
            },
        ),
        types.Tool(
            name="skill_create",
            description=(
                "Scaffold a new skill in the global skills directory. "
                "Creates skill.toml, src/main.py, and requirements.txt from templates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string", "description": "Skill identifier (snake_case)"},
                    "description": {"type": "string"},
                    "runtime":     {
                        "type": "string",
                        "enum": ["python", "node", "binary", "none"],
                        "default": "python",
                    },
                    "author":      {"type": "string", "default": ""},
                },
                "required": ["name", "description"],
            },
        ),
        types.Tool(
            name="skill_register",
            description="(Re)register an installed skill with Claude Code and/or Codex.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":  {"type": "string"},
                    "hosts": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["claude_code", "codex"]},
                        "description": "Hosts to register with (default: all enabled in manifest).",
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="skill_unregister",
            description="Remove a skill from Claude Code and/or Codex configs (keeps files).",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":  {"type": "string"},
                    "hosts": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["claude_code", "codex"]},
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="skill_rebuild_env",
            description="Destroy and recreate the runtime environment (venv/node_modules) for a skill.",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        ),
        types.Tool(
            name="protocol_info",
            description=(
                "Describe the skill-mcp-protocol: what it is, how to bootstrap it on a "
                "new host, and how to use it to manage skills. Call this first if you "
                "are unfamiliar with the protocol."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


# ── Tool dispatcher ─────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(
    name: str, arguments: Dict[str, Any]
) -> List[types.TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except Exception as e:
        result = {"error": str(e), "type": type(e).__name__}
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def _dispatch(name: str, args: Dict[str, Any]) -> Any:
    reg = get_registry()

    # ── skill_list ────────────────────────────────────────────────────────
    if name == "skill_list":
        skills = reg.list_all()
        return {
            "count":  len(skills),
            "skills": [
                {
                    "name":         s["name"],
                    "version":      s["version"],
                    "runtime":      s["runtime_type"],
                    "env_ready":    s["env_ready"],
                    "install_path": s["install_path"],
                }
                for s in skills
            ],
        }

    # ── skill_info ────────────────────────────────────────────────────────
    if name == "skill_info":
        skill_name = args["name"]
        manifest = reg.get(skill_name)
        if not manifest:
            return {"error": f"Skill '{skill_name}' not found in registry."}
        env_status = rt_mgr.env_status(manifest)
        host_status = host_config.registration_status(skill_name)
        return {
            **manifest.to_dict(),
            "install_path": str(manifest.install_path),
            "env_status":   env_status,
            "host_status":  host_status,
        }

    # ── skill_install ─────────────────────────────────────────────────────
    if name == "skill_install":
        source = Path(args["source"]).expanduser().resolve()
        rebuild = args.get("rebuild_env", True)
        reg_hosts = args.get("register_hosts", True)

        if str(source).endswith(".tar.gz"):
            result = importer.import_skill(
                source,
                rebuild_env=rebuild,
                register_hosts=reg_hosts,
            )
        else:
            result = importer.import_from_dir(
                source,
                rebuild_env=rebuild,
                register_hosts=reg_hosts,
            )
        return result.to_dict()

    # ── skill_remove ──────────────────────────────────────────────────────
    if name == "skill_remove":
        skill_name = args["name"]
        keep_files = args.get("keep_files", False)
        manifest = reg.get(skill_name)
        if not manifest:
            return {"error": f"Skill '{skill_name}' not found."}

        host_config.unregister(skill_name)
        rt_mgr.remove_env(manifest)
        importer.post_remove(skill_name)

        if not keep_files and manifest.install_path:
            import shutil
            shutil.rmtree(manifest.install_path, ignore_errors=True)

        reg.unregister(skill_name)
        return {"removed": skill_name, "files_kept": keep_files}

    # ── skill_update ──────────────────────────────────────────────────────
    if name == "skill_update":
        skill_name = args["name"]
        source = args.get("source")

        if source:
            src_path = Path(source).expanduser().resolve()
            result = (
                importer.import_skill(src_path)
                if str(src_path).endswith(".tar.gz")
                else importer.import_from_dir(src_path)
            )
            return result.to_dict()

        # Rebuild in-place
        manifest = reg.get(skill_name)
        if not manifest:
            return {"error": f"Skill '{skill_name}' not found."}
        rt_mgr.rebuild_env(manifest)
        reg.mark_env_ready(skill_name, manifest.env_ready)
        return {"updated": skill_name, "env_rebuilt": True}

    # ── skill_export ──────────────────────────────────────────────────────
    if name == "skill_export":
        skill_name = args["name"]
        output_dir = Path(args["output_dir"]) if args.get("output_dir") else None
        manifest = reg.get(skill_name)
        if not manifest:
            return {"error": f"Skill '{skill_name}' not found."}
        archive = exporter.export_skill(manifest, output_dir)
        return {
            "exported": skill_name,
            "archive":  str(archive),
            "includes": ["skill.toml", "src/", "requirements.txt",
                         "SETUP.md", "bootstrap.sh", "agent-setup.json"],
            "excludes": [".venv/", "node_modules/", "__pycache__/"],
        }

    # ── skill_import ──────────────────────────────────────────────────────
    if name == "skill_import":
        package = Path(args["package_path"]).expanduser().resolve()
        install_dir = Path(args["install_dir"]) if args.get("install_dir") else None
        result = importer.import_skill(
            package,
            install_dir=install_dir,
            rebuild_env=args.get("rebuild_env", True),
            register_hosts=args.get("register_hosts", True),
        )
        return result.to_dict()

    # ── skill_create ──────────────────────────────────────────────────────
    if name == "skill_create":
        skill_name = args["name"]
        description = args["description"]
        runtime = args.get("runtime", "python")
        author = args.get("author", "")

        skill_dir = SKILL_MCP_SKILLS / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "src").mkdir(exist_ok=True)

        # skill.toml
        toml_content = _j2.get_template("skill.toml.j2").render(
            name=skill_name, description=description,
            runtime=runtime, author=author,
        )
        (skill_dir / "skill.toml").write_text(toml_content)

        # requirements.txt / package.json
        if runtime == "python":
            (skill_dir / "requirements.txt").write_text("mcp>=1.0.0\n")
            (skill_dir / "src" / "main.py").write_text(_python_stub(skill_name))
        elif runtime == "node":
            (skill_dir / "package.json").write_text(
                json.dumps({"name": skill_name, "version": "0.1.0",
                            "dependencies": {"@modelcontextprotocol/sdk": "latest"}},
                           indent=2)
            )
            (skill_dir / "src" / "main.js").write_text("// TODO: implement MCP server\n")

        return {
            "created":      skill_name,
            "install_path": str(skill_dir),
            "next_steps": [
                f"Edit {skill_dir}/src/main.py to implement your MCP server",
                f"Run: smcp install {skill_dir}",
            ],
        }

    # ── skill_register ────────────────────────────────────────────────────
    if name == "skill_register":
        skill_name = args["name"]
        hosts = args.get("hosts")
        manifest = reg.get(skill_name)
        if not manifest:
            return {"error": f"Skill '{skill_name}' not found."}
        result = host_config.register(manifest, hosts)
        return {"registered": skill_name, "hosts": result}

    # ── skill_unregister ──────────────────────────────────────────────────
    if name == "skill_unregister":
        skill_name = args["name"]
        hosts = args.get("hosts")
        result = host_config.unregister(skill_name, hosts)
        return {"unregistered": skill_name, "hosts": result}

    # ── skill_rebuild_env ─────────────────────────────────────────────────
    if name == "skill_rebuild_env":
        skill_name = args["name"]
        manifest = reg.get(skill_name)
        if not manifest:
            return {"error": f"Skill '{skill_name}' not found."}
        rt_mgr.rebuild_env(manifest)
        reg.mark_env_ready(skill_name, manifest.env_ready)
        return {"rebuilt": skill_name, "env_ready": manifest.env_ready}

    # ── protocol_info ─────────────────────────────────────────────────────
    if name == "protocol_info":
        return {
            "name":    "skill-mcp-protocol",
            "version": "0.1.0",
            "purpose": (
                "Unified manager for AI skills and MCP servers. "
                "Each skill is a self-contained directory with skill.toml, source code, "
                "and a dependency spec. Runtime envs (.venv) are local-only and rebuilt "
                "on import. Export packages include agent-setup.json so any AI agent "
                "can bootstrap the skill without human intervention."
            ),
            "global_paths": {
                "skills":   str(SKILL_MCP_SKILLS),
                "exports":  str(SKILL_MCP_EXPORTS),
                "registry": str(SKILL_MCP_DATA / "registry.toml"),
            },
            "bootstrap_this_protocol": {
                "step_1": "Read agent-setup.json in this repo",
                "step_2": "Create venv: python3 -m venv .venv",
                "step_3": "Install deps: .venv/bin/pip install -r requirements.txt",
                "step_4": "Register with Claude Code (see agent-setup.json → register_claude_code)",
                "step_5": "Register with Codex (see agent-setup.json → register_codex)",
                "automated": "Or just run: bash bootstrap.sh",
            },
            "available_tools": [
                "skill_list", "skill_info", "skill_install", "skill_remove",
                "skill_update", "skill_export", "skill_import", "skill_create",
                "skill_register", "skill_unregister", "skill_rebuild_env",
                "protocol_info",
            ],
        }

    return {"error": f"Unknown tool: {name!r}"}


# ────────────────────────────────────────────────────────────────────────── #
# Stubs                                                                       #
# ────────────────────────────────────────────────────────────────────────────#

def _python_stub(name: str) -> str:
    return f'''\
"""
{name} — MCP server skeleton generated by skill-mcp-protocol.
Replace this with your actual implementation.
"""
import asyncio
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("{name}")


@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="hello",
            description="A placeholder tool.",
            inputSchema={{"type": "object", "properties": {{}}, "required": []}},
        )
    ]


@server.call_tool()
async def call_tool(name, arguments):
    return [types.TextContent(type="text", text=f"Hello from {name}!")]


async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
'''


# ────────────────────────────────────────────────────────────────────────── #
# Entry point                                                                 #
# ────────────────────────────────────────────────────────────────────────────#

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
