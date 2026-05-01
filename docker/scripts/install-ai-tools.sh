#!/usr/bin/env bash
# Install Claude Code and Codex CLI globally via npm
set -euo pipefail

echo "[ai-tools] Installing @anthropic-ai/claude-code and @openai/codex..."

# Ensure npm is on PATH (nvm installs to /usr/local/bin via symlink)
export PATH="/usr/local/bin:${PATH}"

# Increase npm timeout for slow networks
npm config set fetch-timeout 300000
npm config set fetch-retry-mintimeout 20000
npm config set fetch-retry-maxtimeout 120000

npm install -g @anthropic-ai/claude-code --no-fund --no-audit --loglevel warn
npm install -g @openai/codex           --no-fund --no-audit --loglevel warn

# npm global bin may be in nvm's dir rather than /usr/local/bin — symlink both tools
NPM_PREFIX=$(npm prefix -g)
for tool in claude codex; do
    if [ -f "${NPM_PREFIX}/bin/${tool}" ] && ! command -v "${tool}" &>/dev/null; then
        ln -sf "${NPM_PREFIX}/bin/${tool}" "/usr/local/bin/${tool}"
    fi
done

echo "[ai-tools] Claude Code: $(claude --version 2>&1 || echo 'binary present but needs auth')"
echo "[ai-tools] Codex:       $(codex  --version 2>&1 || echo 'binary present but needs auth')"
