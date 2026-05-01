#!/usr/bin/env bash
# Run integration tests inside a Docker container.
# Config files are COPIED writable so tests can modify them.
# Uses host configs if mounted, otherwise falls back to templates.
set -euo pipefail

echo "=== Integration test setup ==="

TEMPLATES="/workspace/docker/templates"

# 1. Copy host configs to writable locations (fall back to templates)
if [ -f /tmp/host-claude.json ]; then
    cp /tmp/host-claude.json /root/.claude.json
    echo "Using host claude.json"
else
    cp "${TEMPLATES}/claude.json" /root/.claude.json
    echo "Using template claude.json"
fi

mkdir -p /root/.codex
if [ -f /tmp/host-codex/config.toml ]; then
    cp /tmp/host-codex/config.toml /root/.codex/config.toml
    echo "Using host codex config.toml"
else
    cp "${TEMPLATES}/codex-config.toml" /root/.codex/config.toml
    echo "Using template codex config.toml"
fi

# Copy auth files if available (needed for network operations)
cp /tmp/host-codex/auth.json /root/.codex/auth.json 2>/dev/null && \
    echo "Using host codex auth.json" || true

# 2. Isolated data dir for registry/skills (clean per run)
export XDG_DATA_HOME="/tmp/smcp-integration-data"
mkdir -p "${XDG_DATA_HOME}"

# 3. Point host_config module at writable copies
export CLAUDE_CONFIG_PATH="/root/.claude.json"
export CODEX_CONFIG_PATH="/root/.codex/config.toml"
export CODEX_HOME="/root/.codex"

# 4. Install project deps
cd /workspace
pip3 install --quiet --break-system-packages \
    tomli-w tomli jinja2 click packaging pytest mcp 2>/dev/null || \
pip3 install --quiet \
    tomli-w tomli jinja2 click packaging pytest mcp

# 5. Install smcp CLI into PATH for CLI workflow tests
export PATH="/root/.local/bin:${PATH}"
mkdir -p /root/.local/bin
VENV_DIR="/tmp/smcp-venv"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --quiet tomli-w tomli jinja2 click packaging mcp 2>/dev/null || true

cat > /root/.local/bin/smcp <<WRAPPER
#!/usr/bin/env bash
exec "${VENV_DIR}/bin/python" "/workspace/src/cli.py" "\$@"
WRAPPER
chmod +x /root/.local/bin/smcp

echo ""
echo "=== Running integration tests ==="
echo "XDG_DATA_HOME=${XDG_DATA_HOME}"
echo "CLAUDE_CONFIG_PATH=${CLAUDE_CONFIG_PATH}"
echo "CODEX_CONFIG_PATH=${CODEX_CONFIG_PATH}"
echo "smcp: $(which smcp)"
echo ""

python3 -m pytest tests/test_integration_*.py -v --tb=short "$@"
