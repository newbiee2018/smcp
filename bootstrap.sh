#!/usr/bin/env bash
# ============================================================
# bootstrap.sh — installs smcp on a new host.
#
# This is the human/script-friendly version of agent-setup.json.
# AI agents should prefer reading agent-setup.json directly.
#
# Usage:
#   chmod +x bootstrap.sh
#   ./bootstrap.sh
#
# After running, the `smcp` CLI is available at ~/.local/bin/smcp.
# ============================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║      smcp  bootstrap                              ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Repo dir : $REPO_DIR"
echo ""

# ── Step 1: Check Python ──────────────────────────────────────────────────
echo "[1/3] Checking Python 3.8+ ..."
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found on PATH." >&2
  echo "       Install Python 3.8+ and re-run." >&2
  exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MIN=$(python3 -c "import sys; print(1 if sys.version_info >= (3, 8) else 0)")
if [ "$PY_MIN" = "0" ]; then
  echo "ERROR: Python 3.8+ required, found $PY_VER." >&2
  exit 1
fi
echo "      Found Python $PY_VER"

# ── Step 2: Install via smcp CLI ──────────────────────────────────────────
echo "[2/3] Installing smcp ..."
python3 "$REPO_DIR/src/cli.py" install "$REPO_DIR"

# ── Step 3: Verify ────────────────────────────────────────────────────────
echo "[3/3] Verifying installation ..."
export PATH="$HOME/.local/bin:$PATH"
if command -v smcp &>/dev/null; then
  smcp list
  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  smcp is ready!                                                  ║"
  echo "║                                                                  ║"
  echo "║  The smcp CLI is installed at ~/.local/bin/smcp                  ║"
  echo "║  Make sure ~/.local/bin is in your PATH.                         ║"
  echo "║                                                                  ║"
  echo "║  Try: smcp list                                                  ║"
  echo "║       smcp install <path-to-skill>                               ║"
  echo "╚══════════════════════════════════════════════════════════════════╝"
else
  echo "WARNING: smcp not found in PATH." >&2
  echo "         Add ~/.local/bin to your PATH:" >&2
  echo "         export PATH=\"\$HOME/.local/bin:\$PATH\"" >&2
fi
