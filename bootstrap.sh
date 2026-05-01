#!/usr/bin/env bash
# ============================================================
# bootstrap.sh — bootstraps skill-mcp-protocol on a new host.
#
# This is the human/script-friendly version of agent-setup.json.
# An AI agent should prefer reading agent-setup.json directly.
#
# Usage:
#   chmod +x bootstrap.sh
#   ./bootstrap.sh [--install-dir /absolute/path] [--no-register]
#
# Defaults:
#   install-dir : ~/.local/share/skill-mcp/skills/skill-mcp-protocol
#   register    : yes (Claude Code + Codex)
# ============================================================
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DEFAULT_INSTALL="$XDG_DATA_HOME/skill-mcp/skills/skill-mcp-protocol"
INSTALL_DIR="$DEFAULT_INSTALL"
REGISTER=true
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Arg parsing ───────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --install-dir=*) INSTALL_DIR="${arg#*=}" ;;
    --no-register)   REGISTER=false ;;
    -h|--help)
      echo "Usage: $0 [--install-dir=<path>] [--no-register]"
      exit 0
      ;;
  esac
done

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║      skill-mcp-protocol  bootstrap               ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Repo dir    : $REPO_DIR"
echo "  Install dir : $INSTALL_DIR"
echo "  Register    : $REGISTER"
echo ""

# ── Step 1: Check Python ──────────────────────────────────────────────────
echo "[1/6] Checking Python 3.10+ ..."
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found on PATH." >&2
  echo "       Install Python 3.10+ and re-run." >&2
  exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "      Found Python $PY_VER"

# ── Step 2: Copy files to global install dir ─────────────────────────────
echo "[2/6] Copying files to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
if command -v rsync &>/dev/null; then
  rsync -a \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='node_modules' \
    --exclude='.git' \
    "$REPO_DIR/" "$INSTALL_DIR/"
else
  cp -r "$REPO_DIR/." "$INSTALL_DIR/"
  rm -rf "$INSTALL_DIR/.venv" "$INSTALL_DIR/__pycache__"
fi

# ── Step 3: Create venv ───────────────────────────────────────────────────
VENV_DIR="$INSTALL_DIR/.venv"
echo "[3/6] Creating virtual environment at $VENV_DIR ..."
if [ -d "$VENV_DIR" ]; then
  echo "      Existing .venv found — skipping creation."
else
  python3 -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ── Step 4: Install dependencies ─────────────────────────────────────────
echo "[4/6] Installing dependencies ..."
"$VENV_PIP" install --upgrade pip --quiet
"$VENV_PIP" install -r "$INSTALL_DIR/requirements.txt" --quiet
echo "      Done."

# ── Step 5: Register with hosts ───────────────────────────────────────────
ENTRY_PY="$INSTALL_DIR/src/main.py"

if [ "$REGISTER" = true ]; then
  echo "[5/6] Registering with Claude Code and Codex ..."

  # -- Claude Code (~/.claude.json) --
  python3 - << PYEOF
import json, pathlib

cfg_path = pathlib.Path.home() / ".claude.json"
data = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
data.setdefault("mcpServers", {})["skill-mcp-protocol"] = {
    "type":    "stdio",
    "command": "$VENV_PYTHON",
    "args":    ["$ENTRY_PY"],
    "env":     {},
}
cfg_path.write_text(json.dumps(data, indent=2))
print("      Claude Code -> ~/.claude.json  ✓")
PYEOF

  # -- Codex (~/.codex/config.toml) --
  CODEX_CFG="$HOME/.codex/config.toml"
  mkdir -p "$HOME/.codex"
  if grep -q "\[mcp_servers\.skill-mcp-protocol\]" "$CODEX_CFG" 2>/dev/null; then
    echo "      Codex: already registered — skipping."
  else
    cat >> "$CODEX_CFG" << TOML

[mcp_servers.skill-mcp-protocol]
command = "$VENV_PYTHON"
args    = ["$ENTRY_PY"]
TOML
    echo "      Codex  -> ~/.codex/config.toml  ✓"
  fi
else
  echo "[5/6] Skipping host registration (--no-register)."
fi

# ── Step 6: Verify ────────────────────────────────────────────────────────
echo "[6/6] Verifying installation ..."
"$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '$INSTALL_DIR/src')
from manager.registry import get_registry
print('      skill-mcp-protocol OK ✓')
"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  skill-mcp-protocol is ready!                                   ║"
echo "║                                                                  ║"
echo "║  Restart Claude Code / Codex to pick up the new MCP server.     ║"
echo "║  Then try: skill_list  or  smcp list                            ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
