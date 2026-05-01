---
name: skill-mcp-protocol
description: Install, manage, export, and import MCP servers and AI skills with isolated runtime environments. Use this skill when a user asks to install an MCP server, manage skills, or set up a new tool.
metadata:
  short-description: Manage MCP servers and skills with isolated runtimes
---

# Skill MCP Protocol

Manages MCP servers and AI skills across Claude Code and Codex with isolated runtime environments (Python venv, Node node_modules) per skill.

## When to Use

Use this skill when the user asks to:
- Install an MCP server or skill (from GitHub URL, local path, or archive)
- List, remove, update, or export installed skills
- Check what MCP servers are registered
- Transfer skills between hosts

## How to Install a Skill

This skill provides MCP tools. Call them directly:

### From a GitHub URL

1. Clone the repo locally:
   ```bash
   git clone --depth 1 <url> /tmp/skill-clone
   ```

2. If the repo has no `skill.toml`, create one (see format below).

3. Call the MCP tool:
   ```
   skill_install(source="/tmp/skill-clone")
   ```

### From a local directory

```
skill_install(source="/path/to/skill-dir")
```

### From a .skill.tar.gz archive

```
skill_import(package_path="/path/to/skill.tar.gz")
```

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `skill_list` | List all installed skills |
| `skill_info` | Get details about a skill |
| `skill_install` | Install from local dir or archive |
| `skill_import` | Import a .skill.tar.gz archive |
| `skill_export` | Export a skill to portable archive |
| `skill_remove` | Uninstall a skill |
| `skill_create` | Scaffold a new skill from templates |
| `skill_register` | Re-register with Claude Code / Codex |
| `skill_unregister` | Remove from host configs (keep files) |
| `skill_rebuild_env` | Recreate runtime environment |
| `protocol_info` | Full protocol description and paths |

## skill.toml Format

Every managed skill needs a `skill.toml`:

```toml
[skill]
name = "my-skill"
version = "1.0.0"
description = "What this skill does"
author = "name"
tags = ["mcp"]

[runtime]
type = "python"  # or "node" or "binary"
install_cmd = "pip install -r requirements.txt"

[mcp]
entrypoint = "src/main.py"
transport = "stdio"

[hosts]
claude_code = true
codex = true
```

## CLI

The `smcp` command is also available:

```bash
smcp list
smcp info <name>
smcp install <path>
smcp export <name>
smcp remove <name>
```

## Key Paths

- Skills: `~/.local/share/skill-mcp/skills/<name>/`
- Exports: `~/.local/share/skill-mcp/exports/`
- Registry: `~/.local/share/skill-mcp/registry.toml`
- Each skill's runtime: `~/.local/share/skill-mcp/skills/<name>/.venv/`
