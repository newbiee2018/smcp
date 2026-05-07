---
name: skill-mcp-protocol
description: Unified manager for AI skills and MCP servers. Install, export, import, and register skills and MCP servers across Claude Code and Codex.
---

# skill-mcp-protocol

Unified manager for AI skills and MCP servers across Claude Code and Codex — install, update, remove, export, import, and register them with a single CLI.

## When to Use

Use this skill when the user asks to:
- Install an MCP server or skill (from GitHub URL, local path, or archive)
- List, remove, update, or export installed skills or MCP servers
- Check what MCP servers are registered
- Transfer skills or MCP servers between hosts

## How to Install a Skill or MCP Server

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
| `smcp list` | List all installed skills and MCP servers |
| `smcp info <name>` | Get details about a skill or MCP server |
| `smcp install <path>` | Install from local dir or archive |
| `smcp remove <name>` | Uninstall a skill or MCP server |
| `smcp update <name>` | Rebuild env in-place or from new source |
| `smcp export <name>` | Export to portable .skill.tar.gz |
| `smcp import <archive>` | Import a .skill.tar.gz archive |
| `smcp create <name> --description "..."` | Scaffold a new skill or MCP server |
| `smcp register <name>` | Re-register with Claude Code / Codex |
| `smcp unregister <name>` | Remove from host configs (keep files) |
| `smcp rebuild-env <name>` | Recreate runtime environment |

## Alternative: MCP Server Mode

By default, smcp is CLI-only. To also enable MCP server mode (structured tool calls instead of shell commands):

```bash
smcp register skill-mcp-protocol --hosts claude_code --hosts codex
```

This adds smcp as an MCP server in host configs, exposing tools like `skill_install`, `skill_list`, `skill_remove`, etc. To revert to CLI-only:

```bash
smcp unregister skill-mcp-protocol --hosts claude_code --hosts codex
```

## skill.toml Format

Every managed skill or MCP server needs a `skill.toml`:

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
claude_code = true   # register as MCP server in Claude Code
codex = true         # register as MCP server in Codex
```

## Manual Installation

```bash
git clone https://github.com/newbiee2018/smcp.git /tmp/smcp
cd /tmp/smcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Install CLI wrapper
mkdir -p ~/.local/bin
cat > ~/.local/bin/smcp << 'EOF'
#!/usr/bin/env bash
exec "/tmp/smcp/.venv/bin/python" "/tmp/smcp/src/cli.py" "$@"
EOF
chmod +x ~/.local/bin/smcp

# Or let smcp install itself properly:
.venv/bin/python src/cli.py install /tmp/smcp
```

## Uninstallation

```bash
smcp remove skill-mcp-protocol
# Also remove CLI wrapper:
rm ~/.local/bin/smcp
```

## Key Paths

- Skills and MCP servers: `~/.local/share/skill-mcp/skills/<name>/`
- Exports: `~/.local/share/skill-mcp/exports/`
- Registry: `~/.local/share/skill-mcp/registry.toml`
- Each entry's runtime: `~/.local/share/skill-mcp/skills/<name>/.venv/`
