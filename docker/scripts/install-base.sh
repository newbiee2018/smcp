#!/usr/bin/env bash
# Install base system packages required on all Ubuntu versions (20.04+)
set -euo pipefail
UBUNTU_VERSION="${1:-22.04}"

echo "[base] Ubuntu ${UBUNTU_VERSION} — installing base packages..."

# Configure apt to retry on network failures (flaky connections)
cat > /etc/apt/apt.conf.d/80retries << 'APT_CONF'
APT::Acquire::Retries "5";
APT::Acquire::http::Timeout "120";
APT::Acquire::https::Timeout "120";
APT_CONF

apt-get update -qq || true

# Core tools — install with --fix-missing to recover from single-package failures
apt-get install -y --no-install-recommends --fix-missing \
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    software-properties-common \
    build-essential \
    xz-utils \
    rsync \
    unzip \
    sudo

# Best-effort extras (may not exist on every release, especially 18.04 EOL)
apt-get install -y --no-install-recommends --fix-missing \
    lsb-release \
    jq \
    libssl-dev \
    libffi-dev \
    zlib1g-dev 2>/dev/null || true

apt-get clean
rm -rf /var/lib/apt/lists/*
echo "[base] done."
