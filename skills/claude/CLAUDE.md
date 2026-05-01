# skill-mcp-protocol

This host has the `smcp` CLI installed for managing MCP servers and AI skills with isolated runtime environments.

## Installing a new skill

Use shell commands to install skills:

1. **From a GitHub repo**:
   ```bash
   git clone --depth 1 <github-url> /tmp/skill-clone
   smcp install /tmp/skill-clone
   ```

2. **From a local directory**:
   ```bash
   smcp install /path/to/skill-dir
   ```

3. **From an archive**:
   ```bash
   smcp import /path/to/skill.tar.gz
   ```

If the repo has no `skill.toml`, create one first. See `smcp create` for scaffolding.

## CLI commands

```
smcp list                          # list installed skills
smcp info <name>                   # details about a skill
smcp install <path>                # install from local dir or archive
smcp remove <name>                 # uninstall
smcp update <name>                 # rebuild env or update from new source
smcp export <name>                 # export to portable archive
smcp import <archive>              # import a .skill.tar.gz
smcp create <name> --description   # scaffold new skill
smcp register <name>               # re-register with host configs
smcp unregister <name>             # remove from host configs
smcp rebuild-env <name>            # recreate runtime environment
```

## Key rule

Each skill gets its own isolated runtime (`.venv/` for Python, `node_modules/` for Node.js). Exports never include runtime artifacts — they are rebuilt on import.
