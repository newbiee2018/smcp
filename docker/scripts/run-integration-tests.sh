#!/usr/bin/env bash
# Run integration tests inside a Docker container.
# Config files are COPIED writable so tests can modify them.
set -euo pipefail

echo "=== Integration test setup ==="

# 1. Copy host configs to writable locations
cp /tmp/host-claude.json /root/.claude.json 2>/dev/null || echo '{}' > /root/.claude.json
mkdir -p /root/.codex
cp /tmp/host-codex/config.toml /root/.codex/config.toml 2>/dev/null || true
cp /tmp/host-codex/auth.json   /root/.codex/auth.json   2>/dev/null || true

# 2. Isolated data dir for registry/skills (clean per run)
export XDG_DATA_HOME="/tmp/smcp-integration-data"
mkdir -p "${XDG_DATA_HOME}"

# 3. Point host_config module at writable copies
export CLAUDE_CONFIG_PATH="/root/.claude.json"
export CODEX_CONFIG_PATH="/root/.codex/config.toml"

# 4. Install project deps
cd /workspace
pip3 install --quiet --break-system-packages \
    tomli-w tomli jinja2 click packaging pytest 2>/dev/null || \
pip3 install --quiet \
    tomli-w tomli jinja2 click packaging pytest

echo ""
echo "=== Running integration tests ==="
echo "XDG_DATA_HOME=${XDG_DATA_HOME}"
echo "CLAUDE_CONFIG_PATH=${CLAUDE_CONFIG_PATH}"
echo "CODEX_CONFIG_PATH=${CODEX_CONFIG_PATH}"
echo ""

python3 -m pytest tests/test_integration_*.py -v --tb=short -x "$@"
