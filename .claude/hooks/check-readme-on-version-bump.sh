#!/bin/bash
# Stop hook: 版本变更后强制更新 src/jolt_toolkit/README.md
#
# 逻辑：
# 1. 防止无限循环
# 2. 如果 pyproject.toml 中的 version 行有变化，
#    但 src/jolt_toolkit/README.md 没有被修改，则 block

INPUT=$(cat)

if echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

# 检查 pyproject.toml version 行是否有变化
VERSION_CHANGED=$(git diff HEAD -- pyproject.toml 2>/dev/null | grep -E '^\+.*version\s*=' | head -1)
VERSION_STAGED=$(git diff --cached -- pyproject.toml 2>/dev/null | grep -E '^\+.*version\s*=' | head -1)

if [ -z "$VERSION_CHANGED" ] && [ -z "$VERSION_STAGED" ]; then
    exit 0
fi

# 版本有变化，检查 README.md 是否也更新了
PKG_README_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep '^src/jolt_toolkit/README.md$')
PKG_README_STAGED=$(git diff --cached --name-only 2>/dev/null | grep '^src/jolt_toolkit/README.md$')
# 也检查未跟踪的新文件（重构后 README 可能是 untracked）
PKG_README_UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null | grep '^src/jolt_toolkit/README.md$')

if [ -z "$PKG_README_CHANGED" ] && [ -z "$PKG_README_STAGED" ] && [ -z "$PKG_README_UNTRACKED" ]; then
    echo '{"decision": "block", "reason": "[doc-hook] 检测到 pyproject.toml 版本号已变更但 src/jolt_toolkit/README.md 未更新。根据 CLAUDE.md 规范，每次版本变更后必须先更新此架构文档。请更新 src/jolt_toolkit/README.md 以反映本次变更。"}'
    exit 0
fi

exit 0
