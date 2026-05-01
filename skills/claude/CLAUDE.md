# skill-mcp-protocol

This host has the skill-mcp-protocol MCP server installed. It manages MCP servers and AI skills with isolated runtime environments.

## Installing a new skill

To install an MCP server or skill, use the MCP tools provided by `skill-mcp-protocol`:

1. **From a GitHub repo**: Clone it, then call `skill_install`:
   ```
   git clone --depth 1 <github-url> /tmp/skill-clone
   ```
   Then use the `skill_install` MCP tool with `source: "/tmp/skill-clone"`.

2. **From a local directory**: Call `skill_install` with the path.

3. **From an archive**: Call `skill_import` with the `.skill.tar.gz` path.

If the repo has no `skill.toml`, create one first (see `protocol_info` tool for the format).

## Available MCP tools

- `skill_list` — list installed skills
- `skill_info` — details about a skill
- `skill_install` — install from local path or archive
- `skill_import` — import a .skill.tar.gz
- `skill_export` — export to portable archive
- `skill_remove` — uninstall
- `skill_create` — scaffold new skill
- `protocol_info` — full protocol docs

## Key rule

Each skill gets its own isolated runtime (`.venv/` for Python, `node_modules/` for Node.js). Exports never include runtime artifacts — they are rebuilt on import.
