# ============================================================
# skill-mcp-protocol test environment (Ubuntu 20.04+, Python ≥3.8)
# Usage: docker build --build-arg UBUNTU_VERSION=22.04 -t smcp-test:22.04 .
# ============================================================
ARG UBUNTU_VERSION=22.04
FROM ubuntu:${UBUNTU_VERSION}

# Re-declare after FROM so it's visible in the build stage
ARG UBUNTU_VERSION=22.04
ARG NODE_MAJOR=24

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV NVM_DIR=/root/.nvm
ENV NODE_MAJOR=${NODE_MAJOR}

WORKDIR /setup

# ── 1. Base system packages ──────────────────────────────────────────────────
COPY scripts/install-base.sh .
RUN bash install-base.sh "${UBUNTU_VERSION}"

# ── 2. Python 3.10+ (deadsnakes for 18.04 and 20.04) ────────────────────────
COPY scripts/install-python.sh .
RUN bash install-python.sh "${UBUNTU_VERSION}"

# ── 3. nvm + Node.js ─────────────────────────────────────────────────────────
COPY scripts/install-nvm-node.sh .
RUN bash install-nvm-node.sh "${NODE_MAJOR}"

# ── 4. Claude Code + Codex via npm ───────────────────────────────────────────
COPY scripts/install-ai-tools.sh .
RUN bash install-ai-tools.sh

# ── 5. Test / verify script ───────────────────────────────────────────────────
COPY scripts/test-env.sh /usr/local/bin/test-env
RUN chmod +x /usr/local/bin/test-env

# Source nvm in all bash sessions
RUN echo 'export NVM_DIR="/root/.nvm"' >> /root/.bashrc && \
    echo '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"' >> /root/.bashrc

WORKDIR /workspace
CMD ["/bin/bash"]
