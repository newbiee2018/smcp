---
name: skill-mcp-protocol
description: Install, manage, export, and import MCP servers and AI skills with isolated runtime environments. Use this skill when a user asks to install an MCP server, manage skills, or set up a new tool.
metadata:
  short-description: Manage MCP servers and skills via the smcp CLI
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

Use the `smcp` CLI. All commands output structured JSON.

### From a GitHub URL

```bash
git clone --depth 1 <url> /tmp/skill-clone
smcp install /tmp/skill-clone
```

If the repo has no `skill.toml`, create one first (see format below).

### From a local directory

```bash
smcp install /path/to/skill-dir
```

### From a .skill.tar.gz archive

```bash
smcp import /path/to/skill.tar.gz
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `smcp list` | List all installed skills |
| `smcp info <name>` | Get details about a skill |
| `smcp install <path>` | Install from local dir or archive |
| `smcp remove <name>` | Uninstall a skill |
| `smcp update <name>` | Rebuild env in-place or from new source |
| `smcp export <name>` | Export to portable .skill.tar.gz |
| `smcp import <archive>` | Import a .skill.tar.gz archive |
| `smcp create <name> --description "..."` | Scaffold a new skill |
| `smcp register <name>` | Re-register with Claude Code / Codex |
| `smcp unregister <name>` | Remove from host configs (keep files) |
| `smcp rebuild-env <name>` | Recreate runtime environment |

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
type = "python"  # or "node", "binary", "none"
install_cmd = "pip install -r requirements.txt"

[mcp]
entrypoint = "src/main.py"
transport = "stdio"

[hosts]
claude_code = true
codex = true
```

## Key Paths

- Skills: `~/.local/share/skill-mcp/skills/<name>/`
- Exports: `~/.local/share/skill-mcp/exports/`
- Registry: `~/.local/share/skill-mcp/registry.toml`
- Each skill's runtime: `~/.local/share/skill-mcp/skills/<name>/.venv/`
