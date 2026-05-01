#!/usr/bin/env bash
# Run all unit tests.
# Usage (from repo root):
#   bash tests/run_tests.sh              # uses system python3
#   bash tests/run_tests.sh /path/venv   # uses a specific venv
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${1:-python3}"

echo "=== skill-mcp-protocol test suite ==="
echo "Python : $("${PYTHON}" --version)"
echo "Repo   : ${REPO}"
echo ""

cd "${REPO}"

# Install test deps if not already available
# --break-system-packages needed on Ubuntu 24.04+ (PEP 668)
"${PYTHON}" -m pip install --quiet tomli-w tomli jinja2 click packaging pytest 2>/dev/null || \
"${PYTHON}" -m pip install --quiet --break-system-packages tomli-w tomli jinja2 click packaging pytest 2>/dev/null || true

# Discover and run all test_*.py files
"${PYTHON}" -m pytest tests/ -v --tb=short 2>/dev/null || \
"${PYTHON}" -m unittest discover -s tests -p "test_*.py" -v

echo ""
echo "=== done ==="
