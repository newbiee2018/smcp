# skill-mcp-protocol — Setup Guide

> The unified manager for AI skills and MCP servers.  
> Bootstrap **this** protocol first on any new host — then use it to manage all other skills.

## License

This repository is licensed under the MIT License. See [LICENSE](LICENSE).

---

## What This Is

`skill-mcp-protocol` is itself a skill and an MCP server. Once installed it gives
any Claude Code or Codex session these tools:

| Tool | Purpose |
|---|---|
| `skill_list` | List all installed skills |
| `skill_info` | Details about a skill |
| `skill_install` | Install from local dir or `.skill.tar.gz` |
| `skill_remove` | Uninstall a skill |
| `skill_update` | Rebuild/update a skill |
| `skill_export` | Package a skill (code only, no venv) |
| `skill_import` | Import a `.skill.tar.gz` package |
| `skill_create` | Scaffold a new skill |
| `skill_register` / `skill_unregister` | Manage host configs |
| `skill_rebuild_env` | Recreate venv/node_modules |
| `protocol_info` | Describe the protocol to the AI agent |

---

## Global Paths (XDG)

| Purpose | Path |
|---|---|
| Installed skills | `~/.local/share/skill-mcp/skills/<name>/` |
| Exported packages | `~/.local/share/skill-mcp/exports/` |
| Registry | `~/.local/share/skill-mcp/registry.toml` |
| Config | `~/.config/skill-mcp/config.toml` |

The **local workspace** (this repo) is a **draft/development area**.  
Run `smcp install <path>` or `./bootstrap.sh` to promote it to the global location.

---

## Prerequisites

- Python 3.10+
- `pip`

---

## Option A — Automated (recommended)

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

This copies files to `~/.local/share/skill-mcp/skills/skill-mcp-protocol/`,
creates a venv, installs deps, and registers with Claude Code + Codex.

---

## Option B — Manual step by step

```bash
# 1. Clone / extract this repo somewhere
REPO="$(pwd)"

# 2. Define global install dir
INSTALL="$HOME/.local/share/skill-mcp/skills/skill-mcp-protocol"
mkdir -p "$INSTALL"

# 3. Copy files (skip venv)
rsync -a --exclude='.venv' --exclude='__pycache__' "$REPO/" "$INSTALL/"

# 4. Create venv
python3 -m venv "$INSTALL/.venv"

# 5. Install dependencies
"$INSTALL/.venv/bin/pip" install -r "$INSTALL/requirements.txt"

# 6. Register with Claude Code
python3 - << PYEOF
import json, pathlib
cfg = pathlib.Path.home() / ".claude.json"
d = json.loads(cfg.read_text()) if cfg.exists() else {}
d.setdefault("mcpServers", {})["skill-mcp-protocol"] = {
    "type": "stdio",
    "command": "$INSTALL/.venv/bin/python",
    "args": ["$INSTALL/src/main.py"],
    "env": {}
}
cfg.write_text(json.dumps(d, indent=2))
PYEOF

# 7. Register with Codex
mkdir -p ~/.codex
cat >> ~/.codex/config.toml << TOML

[mcp_servers.skill-mcp-protocol]
command = "$INSTALL/.venv/bin/python"
args    = ["$INSTALL/src/main.py"]
TOML
```

---

## Option C — AI Agent (reads agent-setup.json)

If you are an AI agent in a new session:

1. Read `agent-setup.json` in this directory
2. Set `{repo_dir}` to the absolute path of this directory
3. Execute each step in `setup_steps` in order
4. After completion, the MCP server is registered and you can call `skill_list`

---

## CLI Usage

After bootstrapping, the `smcp` CLI is available via:

```bash
~/.local/share/skill-mcp/skills/skill-mcp-protocol/.venv/bin/python \
  ~/.local/share/skill-mcp/skills/skill-mcp-protocol/src/cli.py --help
```

Or add an alias:
```bash
alias smcp="~/.local/share/skill-mcp/skills/skill-mcp-protocol/.venv/bin/python \
  ~/.local/share/skill-mcp/skills/skill-mcp-protocol/src/cli.py"
```

### Examples

```bash
smcp list
smcp install ~/my-projects/weather-skill
smcp export weather-skill
smcp import ~/Downloads/weather-skill-1.0.0.skill.tar.gz
smcp remove weather-skill
smcp create my-new-skill --description "Does something cool"
```

---

## Skill Package Format

When you run `smcp export <name>`, the resulting `.skill.tar.gz` contains:

```
<name>-<version>/
├── skill.toml          ← manifest
├── src/                ← source code
├── requirements.txt    ← dep spec
├── SETUP.md            ← human setup guide
├── bootstrap.sh        ← automated setup script
└── agent-setup.json    ← machine-readable setup for AI agents
```

**Excluded** (always rebuilt on target host):
- `.venv/`
- `node_modules/`
- `__pycache__/`

---

## Uninstall

```bash
# Remove skill and host registrations
smcp remove skill-mcp-protocol

# Or manually:
rm -rf ~/.local/share/skill-mcp/skills/skill-mcp-protocol
# Then remove mcpServers.skill-mcp-protocol from ~/.claude.json
# And [mcp_servers.skill-mcp-protocol] from ~/.codex/config.toml
```
