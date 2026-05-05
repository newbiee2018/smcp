# skill-mcp-protocol

Unified CLI tool for managing AI skills and MCP servers with isolated runtime environments.

Install, update, remove, export, and import skills across **Claude Code** and **Codex** with per-skill venvs (`Python`) or `node_modules` (`Node.js`). AI agents discover `smcp` via native skill entries and use it for all operations.

## Quick Start

```bash
git clone https://github.com/newbiee2018/skill-mcp-protocol.git
cd skill-mcp-protocol
python3 src/cli.py install .
```

This creates a venv, installs dependencies, adds `smcp` to `~/.local/bin/`, and creates native skill entries for Claude Code and Codex.

Or use the bootstrap script:

```bash
./bootstrap.sh
```

> **Requires**: Python 3.8+ (3.10+ for MCP server mode), `~/.local/bin` in `PATH`

## Usage

```bash
smcp list                              # list installed skills
smcp info <name>                       # details about a skill
smcp install <path>                    # install from local dir
smcp remove <name>                     # uninstall
smcp update <name>                     # rebuild env or update from new source
smcp export <name>                     # export to portable .skill.tar.gz
smcp import <archive>                  # import a .skill.tar.gz
smcp create <name> --description "..." # scaffold a new skill
smcp register <name>                   # re-register with host configs
smcp unregister <name>                 # remove from host configs
smcp rebuild-env <name>               # recreate runtime environment
```

## Installing a Skill

```bash
# From a GitHub repo
git clone --depth 1 <url> /tmp/skill-clone
smcp install /tmp/skill-clone

# From a local directory
smcp install /path/to/skill-dir

# From an exported archive
smcp import /path/to/skill.skill.tar.gz
```

Each skill gets its own isolated runtime (`.venv/` for Python, `node_modules/` for Node.js). Exports never include runtime artifacts — they are rebuilt on import.

## skill.toml Format

Every managed skill needs a `skill.toml` manifest:

```toml
[skill]
name = "my-skill"
version = "1.0.0"
description = "What this skill does"
author = "name"
tags = ["mcp"]

[runtime]
type = "python"              # "python", "node", "binary", or "none"
install_cmd = "pip install -r requirements.txt"

[mcp]
entrypoint = "src/main.py"
transport = "stdio"

[hosts]
claude_code = true           # register as MCP server in Claude Code
codex = true                 # register as MCP server in Codex
```

Set `runtime.type = "none"` for description-only skills (no venv, no MCP server).

## Architecture

```
~/.local/share/skill-mcp/
├── skills/
│   ├── my-skill/            # installed skill
│   │   ├── skill.toml       # manifest
│   │   ├── src/             # source code
│   │   ├── .venv/           # isolated Python venv
│   │   └── ...
│   └── skill-mcp-protocol/  # this tool (self-managed)
├── exports/                 # exported .skill.tar.gz archives
└── registry.toml            # installed skills registry

~/.claude/skills/<name>/SKILL.md   # Claude Code native skill entry
~/.codex/skills/<name>/SKILL.md    # Codex native skill entry
~/.local/bin/smcp                  # CLI wrapper
```

## MCP Server Mode (Optional)

By default, skill-mcp-protocol is **CLI-only**. AI agents call `smcp` commands directly. To also enable MCP server mode (structured tool calls):

```bash
smcp register skill-mcp-protocol --hosts claude_code --hosts codex
```

This exposes MCP tools (`skill_install`, `skill_list`, `skill_remove`, etc.) as an alternative to CLI commands. To revert:

```bash
smcp unregister skill-mcp-protocol --hosts claude_code --hosts codex
```

## Uninstallation

```bash
smcp remove skill-mcp-protocol
rm ~/.local/bin/smcp
```

## Testing

Unit tests (no network, fast):

```bash
python3 -m pytest tests/ -v --ignore=tests/test_integration_mcp_install.py \
  --ignore=tests/test_integration_venv_export_import.py \
  --ignore=tests/test_integration_workflow.py
```

Integration tests (requires Docker, network):

```bash
sg docker -c "docker compose -f docker/docker-compose.integration.yml run integration"
```

Or locally:

```bash
SMCP_INTEGRATION=1 python3 -m pytest tests/test_integration_workflow.py -v
```

## License

[MIT](LICENSE)
