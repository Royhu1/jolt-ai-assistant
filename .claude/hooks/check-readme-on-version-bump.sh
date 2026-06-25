#!/bin/bash
# Stop hook: enforce updating src/jolt_toolkit/README.md after a version change
#
# Logic:
# 1. Prevent infinite loops
# 2. If the version line in pyproject.toml has changed,
#    but src/jolt_toolkit/README.md has not been modified, then block

INPUT=$(cat)

if echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

# Check whether the version line in pyproject.toml has changed
VERSION_CHANGED=$(git diff HEAD -- pyproject.toml 2>/dev/null | grep -E '^\+.*version\s*=' | head -1)
VERSION_STAGED=$(git diff --cached -- pyproject.toml 2>/dev/null | grep -E '^\+.*version\s*=' | head -1)

if [ -z "$VERSION_CHANGED" ] && [ -z "$VERSION_STAGED" ]; then
    exit 0
fi

# The version has changed; check whether README.md has been updated as well
PKG_README_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep '^src/jolt_toolkit/README.md$')
PKG_README_STAGED=$(git diff --cached --name-only 2>/dev/null | grep '^src/jolt_toolkit/README.md$')
# Also check for untracked new files (after a refactor the README may be untracked)
PKG_README_UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null | grep '^src/jolt_toolkit/README.md$')

if [ -z "$PKG_README_CHANGED" ] && [ -z "$PKG_README_STAGED" ] && [ -z "$PKG_README_UNTRACKED" ]; then
    echo '{"decision": "block", "reason": "[doc-hook] Detected that the version number in pyproject.toml has changed but src/jolt_toolkit/README.md has not been updated. According to the CLAUDE.md conventions, after every version change you must first update this architecture document. Please update src/jolt_toolkit/README.md to reflect this change."}'
    exit 0
fi

exit 0
