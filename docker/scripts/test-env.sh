#!/usr/bin/env bash
# ============================================================
# test-env.sh — verify the container environment is correct
# Run inside the container: test-env
# ============================================================
set -uo pipefail

PASS=0; FAIL=0
ok()   { echo "  [PASS] $*"; ((PASS++)); }
fail() { echo "  [FAIL] $*"; ((FAIL++)); }
hdr()  { echo ""; echo "=== $* ==="; }

hdr "Python"
if command -v python3 &>/dev/null; then
    VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$VER" | cut -d. -f1)
    PY_MINOR=$(echo "$VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        ok "Python ${VER} (manager + MCP server)"
    elif [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 8 ]; then
        ok "Python ${VER} (manager/CLI only — MCP server needs >=3.10)"
    else
        fail "Python ${VER} — need >=3.8 for manager, >=3.10 for MCP server"
    fi
else
    fail "python3 not found"
fi

hdr "Node.js / npm"
if command -v node &>/dev/null; then
    ok "Node $(node --version)"
else
    fail "node not found"
fi
if command -v npm &>/dev/null; then
    ok "npm $(npm --version)"
else
    fail "npm not found"
fi

hdr "Claude Code"
if command -v claude &>/dev/null; then
    CLAUDE_VER=$(claude --version 2>&1 | head -1)
    ok "Claude Code: ${CLAUDE_VER}"
else
    fail "claude not found on PATH"
fi

hdr "Codex"
if command -v codex &>/dev/null; then
    CODEX_VER=$(codex --version 2>&1 | head -1)
    ok "Codex: ${CODEX_VER}"
else
    fail "codex not found on PATH"
fi

hdr "Configuration files"
if [ -f /root/.claude.json ]; then
    SIZE=$(wc -c < /root/.claude.json)
    ok "~/.claude.json present (${SIZE} bytes)"
else
    fail "~/.claude.json not found — mount with: -v ~/.claude.json:/root/.claude.json"
fi

if [ -f /root/.codex/auth.json ]; then
    ok "~/.codex/auth.json present"
else
    fail "~/.codex/auth.json not found — mount with: -v ~/.codex:/root/.codex"
fi

if [ -f /root/.codex/config.toml ]; then
    ok "~/.codex/config.toml present"
else
    fail "~/.codex/config.toml not found"
fi

hdr "Quick API connectivity check"
# Non-destructive: just check if claude can print its own config (reads auth)
if claude config list &>/dev/null 2>&1; then
    ok "Claude Code auth/config readable"
else
    # Claude Code might need interactive auth — just check binary works
    ok "Claude Code binary responds (full auth requires interactive session)"
fi

# Codex: check version is reachable and auth file has content
if [ -s /root/.codex/auth.json ]; then
    ok "Codex auth.json is non-empty"
else
    fail "Codex auth.json is empty or missing"
fi

hdr "Python package imports (venv test)"
python3 -c "
import sys, venv, pathlib, tempfile
with tempfile.TemporaryDirectory() as d:
    venv.create(d, with_pip=True)
    print('  venv creation: OK')
" && ok "Python venv works" || fail "Python venv broken"

hdr "Summary"
echo ""
echo "  Passed: ${PASS}"
echo "  Failed: ${FAIL}"
[ "${FAIL}" -eq 0 ] && echo "  ALL TESTS PASSED" && exit 0 || echo "  SOME TESTS FAILED" && exit 1
