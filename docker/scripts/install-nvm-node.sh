#!/usr/bin/env bash
# Install nvm + Node.js inside Docker (root user)
set -euo pipefail
NODE_MAJOR="${1:-24}"
NVM_VERSION="0.40.3"
NVM_DIR="/root/.nvm"

echo "[nvm] Installing nvm ${NVM_VERSION} + Node ${NODE_MAJOR} LTS..."

# Install nvm
curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh" | bash

# Load nvm in this shell
export NVM_DIR="${NVM_DIR}"
# shellcheck source=/dev/null
. "${NVM_DIR}/nvm.sh"

# Install requested Node major (LTS alias within that major)
nvm install "${NODE_MAJOR}"
nvm alias default "${NODE_MAJOR}"
nvm use default

# Hard-link binaries into /usr/local/bin so they work in non-interactive shells
# (RUN commands and docker exec without bash -l)
NODE_BIN_DIR="${NVM_DIR}/versions/node/$(nvm version default)/bin"
for bin in node npm npx; do
    ln -sf "${NODE_BIN_DIR}/${bin}" "/usr/local/bin/${bin}" || true
done

echo "[nvm] Node: $(node --version)  npm: $(npm --version)"

# Persist nvm sourcing for interactive bash sessions
{
    echo 'export NVM_DIR="/root/.nvm"'
    echo '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"'
    echo '[ -s "$NVM_DIR/bash_completion" ] && . "$NVM_DIR/bash_completion"'
} >> /root/.bashrc
