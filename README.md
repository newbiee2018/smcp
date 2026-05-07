# smcp

Unified manager for AI skills and MCP servers across **Claude Code** and **Codex**.

Install, update, remove, export, and import skills and MCP servers — each bundled with its source, dependencies, and host registration config in a single `skill.toml` manifest. Runtime environments (Python venv, Node node_modules) are managed per entry to keep dependencies from conflicting. AI agents discover `smcp` via native skill entries and use it for all operations.

An MCP server (e.g., `ida-mcp`) is registered in host configs (`~/.claude.json`, `~/.codex/config.toml`) so the AI agent can call its tools via the MCP protocol. A skill (e.g., `skill-mcp-protocol` itself) provides CLI commands or description-only instructions without an MCP server registration. `smcp list` shows the type of each entry.

## Quick Start

```bash
git clone https://github.com/newbiee2018/smcp.git
cd smcp
python3 -m venv .bootstrap-venv
.bootstrap-venv/bin/pip install -r requirements.txt
.bootstrap-venv/bin/python src/cli.py install .
```

This installs the `smcp` CLI to `~/.local/bin/`, sets up dependencies, and creates native skill entries named `skill-mcp-protocol` for Claude Code and Codex.

Or use the bootstrap script:

```bash
./bootstrap.sh
```

> **Requires**: Python 3.8+ (3.10+ for MCP server mode), `~/.local/bin` in `PATH`

## Usage

```bash
smcp list                              # list installed skills and MCP servers
smcp info <name>                       # details about a skill or MCP server
smcp install <path>                    # install from local dir
smcp remove <name>                     # uninstall
smcp update <name>                     # rebuild env or update from new source
smcp export <name>                     # export to portable .skill.tar.gz
smcp import <archive>                  # import a .skill.tar.gz
smcp create <name> --description "..." # scaffold a new skill or MCP server
smcp register <name>                   # re-register with host configs
smcp unregister <name>                 # remove from host configs
smcp rebuild-env <name>               # recreate runtime environment
```

## Installing a Skill

There are three ways to install a skill or MCP server, depending on what's available on the host.

### 1. Via smcp CLI (recommended)

```bash
# From a local directory
smcp install /path/to/skill-dir

# From a GitHub repo
git clone --depth 1 <url> /tmp/skill-clone
smcp install /tmp/skill-clone

# From an exported archive
smcp import /path/to/skill.skill.tar.gz
```

This handles everything: copies source, creates the runtime environment, installs dependencies, registers with host configs, and creates native skill entries.

### 2. Via MCP server tools (for AI agents)

If smcp is already installed and running in MCP server mode, AI agents can call structured tools instead of shell commands:

```
skill_install(source="/path/to/skill-dir")
skill_import(package="/path/to/archive.skill.tar.gz")
skill_list()
skill_remove(name="my-skill")
```

Enable MCP server mode first: `smcp register skill-mcp-protocol --hosts claude_code --hosts codex`

### 3. Manual installation (when smcp is not available)

When neither the smcp CLI nor MCP tools are available (e.g., fresh host, air-gapped environment), install manually:

```bash
# Variables — adjust to your skill
SKILL_NAME="my-skill"
SKILL_SRC="/path/to/skill-source"
INSTALL_DIR="$HOME/.local/share/skill-mcp/skills/$SKILL_NAME"

# 1. Copy source files
mkdir -p "$INSTALL_DIR"
rsync -a --exclude='.venv' --exclude='node_modules' --exclude='__pycache__' \
  "$SKILL_SRC/" "$INSTALL_DIR/"

# 2. Create virtual environment (Python skills)
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 3. Register as MCP server in Claude Code (~/.claude.json)
python3 - <<PYEOF
import json, pathlib
cfg = pathlib.Path.home() / ".claude.json"
data = json.loads(cfg.read_text()) if cfg.exists() else {}
data.setdefault("mcpServers", {})["$SKILL_NAME"] = {
    "type": "stdio",
    "command": "$INSTALL_DIR/.venv/bin/python",
    "args": ["$INSTALL_DIR/src/main.py"],
    "env": {}
}
cfg.write_text(json.dumps(data, indent=2))
PYEOF

# 4. Register as MCP server in Codex (~/.codex/config.toml)
mkdir -p ~/.codex
cat >> ~/.codex/config.toml <<TOML

[mcp_servers.$SKILL_NAME]
command = "$INSTALL_DIR/.venv/bin/python"
args    = ["$INSTALL_DIR/src/main.py"]
TOML

# 5. Create native skill entry for Claude Code
mkdir -p "$HOME/.claude/skills/$SKILL_NAME"
cat > "$HOME/.claude/skills/$SKILL_NAME/SKILL.md" <<'MD'
---
name: my-skill
description: What this skill does
---
# my-skill
Instructions for Claude Code to use this skill.
MD

# 6. Create native skill entry for Codex
mkdir -p "$HOME/.codex/skills/$SKILL_NAME"
cat > "$HOME/.codex/skills/$SKILL_NAME/SKILL.md" <<'MD'
---
name: my-skill
description: What this skill does
---
# my-skill
Instructions for Codex to use this skill.
MD

# 7. Add to smcp registry (so smcp can manage it later)
python3 - <<PYEOF
import tomllib, pathlib
reg_path = pathlib.Path.home() / ".local/share/skill-mcp/registry.toml"
reg_path.parent.mkdir(parents=True, exist_ok=True)
data = {}
if reg_path.exists():
    with open(reg_path, "rb") as f:
        data = tomllib.load(f)
data.setdefault("skills", {})["$SKILL_NAME"] = {
    "version": "1.0.0",
    "path": "$INSTALL_DIR",
    "runtime": "python"
}
lines = ["[skills]"]
for k, v in data.get("skills", {}).items():
    lines.append(f'[skills.{k}]')
    for vk, vv in v.items():
        lines.append(f'{vk} = {repr(vv)}')
reg_path.write_text("\n".join(lines) + "\n")
PYEOF
```

For Node.js skills, replace the venv step with `npm install` in the skill directory and adjust the `command`/`args` in host configs accordingly.

Steps 3–6 are optional depending on which hosts you use. Skip Codex steps if you only use Claude Code, and vice versa. Skip MCP registration (steps 3–4) if the skill has no MCP server (`runtime.type = "none"` in skill.toml).

### Export / Import

Exports bundle source and dependency specs into a portable `.skill.tar.gz` — runtime artifacts (`.venv/`, `node_modules/`) are excluded and rebuilt automatically on the target host.

## skill.toml Format

Every managed skill or MCP server needs a `skill.toml` manifest:

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

Set `runtime.type = "none"` for description-only skills (no venv, no MCP server). Set `hosts.claude_code` and/or `hosts.codex` to `true` to register as an MCP server in the corresponding host; set both to `false` for a CLI-only skill.

## Architecture

```
~/.local/share/skill-mcp/
├── skills/
│   ├── my-skill/            # installed skill or MCP server
│   │   ├── skill.toml       # manifest
│   │   ├── src/             # source code
│   │   ├── .venv/           # per-skill Python venv (auto-managed)
│   │   └── ...
│   └── skill-mcp-protocol/  # smcp itself (self-managed)
├── exports/                 # exported .skill.tar.gz archives
└── registry.toml            # installed skills registry

~/.claude/skills/skill-mcp-protocol/SKILL.md  # Claude Code native skill entry
~/.codex/skills/skill-mcp-protocol/SKILL.md    # Codex native skill entry
~/.local/bin/smcp                               # CLI wrapper
```

## MCP Server Mode (Optional)

By default, smcp is **CLI-only**. AI agents call `smcp` commands directly. To also enable MCP server mode (structured tool calls):

```bash
smcp register skill-mcp-protocol --hosts claude_code --hosts codex
```

This exposes MCP tools (`skill_install`, `skill_list`, `skill_remove`, etc.) as an alternative to CLI commands. To revert:

```bash
smcp unregister skill-mcp-protocol --hosts claude_code --hosts codex
```

## Uninstallation

Via smcp CLI:

```bash
smcp remove <name>
```

To uninstall smcp itself:

```bash
smcp remove skill-mcp-protocol
rm ~/.local/bin/smcp
```

Manual uninstall (reverse of manual installation):

```bash
SKILL_NAME="my-skill"

# Remove MCP registration from Claude Code
python3 -c "
import json, pathlib
cfg = pathlib.Path.home() / '.claude.json'
if cfg.exists():
    d = json.loads(cfg.read_text())
    d.get('mcpServers', {}).pop('$SKILL_NAME', None)
    cfg.write_text(json.dumps(d, indent=2))
"

# Remove MCP registration from Codex (~/.codex/config.toml)
# Edit the file and delete the [mcp_servers.<name>] block

# Remove native skill entries
rm -rf ~/.claude/skills/$SKILL_NAME
rm -rf ~/.codex/skills/$SKILL_NAME

# Remove skill files
rm -rf ~/.local/share/skill-mcp/skills/$SKILL_NAME
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
