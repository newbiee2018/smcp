#!/usr/bin/env bash
# Use the builtin system Python3 on each Ubuntu release:
#   Ubuntu 20.04 → Python 3.8 (manager/CLI only; MCP server needs >=3.10)
#   Ubuntu 22.04 → Python 3.10
#   Ubuntu 24.04 → Python 3.12
set -euo pipefail
UBUNTU_VERSION="${1:-22.04}"

echo "[python] Ubuntu ${UBUNTU_VERSION} — installing builtin Python3 packages..."

apt-get update -qq

# Install venv and pip for the system Python
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-pip

apt-get clean 2>/dev/null || true
rm -rf /var/lib/apt/lists/*

# Symlinks so scripts can use 'python' and 'pip' unversioned
PY_BIN=$(command -v python3)
ln -sf "${PY_BIN}" /usr/local/bin/python

PIP_BIN=$(command -v pip3 2>/dev/null || command -v pip 2>/dev/null || true)
if [ -n "${PIP_BIN}" ]; then
    ln -sf "${PIP_BIN}" /usr/local/bin/pip3 2>/dev/null || true
    ln -sf "${PIP_BIN}" /usr/local/bin/pip  2>/dev/null || true
fi

echo "[python] Installed: $(python3 --version)  pip: $(pip3 --version 2>/dev/null | cut -d' ' -f1-2)"
