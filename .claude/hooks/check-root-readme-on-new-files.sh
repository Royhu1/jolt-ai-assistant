#!/bin/bash
# Stop hook: 新增脚本或工具文件时强制更新根目录 README.md
#
# 逻辑：
# 1. 防止无限循环
# 2. 如果有新增的 .py 或 .sh 文件（untracked 或 newly added），
#    但根目录 README.md 没有被修改，则 block
# 3. 仅检测根目录和 src/jolt_toolkit/ 下的新文件
#    （不包括 cache/、reports/、parameter_identify/ 等辅助目录）

INPUT=$(cat)

if echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

# 检查是否有新增的脚本文件（git diff 中的新文件 + untracked）
NEW_FILES_DIFF=$(git diff --name-only --diff-filter=A HEAD 2>/dev/null | grep -E '^(src/jolt_toolkit/[^/]+\.py|[^/]+\.(py|sh))$' | head -1)
NEW_FILES_STAGED=$(git diff --cached --name-only --diff-filter=A 2>/dev/null | grep -E '^(src/jolt_toolkit/[^/]+\.py|[^/]+\.(py|sh))$' | head -1)
NEW_UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null | grep -E '^(src/jolt_toolkit/[^/]+\.py|[^/]+\.(py|sh))$' | head -1)

if [ -z "$NEW_FILES_DIFF" ] && [ -z "$NEW_FILES_STAGED" ] && [ -z "$NEW_UNTRACKED" ]; then
    exit 0
fi

# 有新文件，检查根 README.md 是否更新
ROOT_README_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep '^README.md$')
ROOT_README_STAGED=$(git diff --cached --name-only 2>/dev/null | grep '^README.md$')

if [ -z "$ROOT_README_CHANGED" ] && [ -z "$ROOT_README_STAGED" ]; then
    NEW_LIST="${NEW_FILES_DIFF}${NEW_FILES_STAGED}${NEW_UNTRACKED}"
    echo "{\"decision\": \"block\", \"reason\": \"[doc-hook] 检测到新增了脚本/工具文件但根目录 README.md 未更新。根据 CLAUDE.md 规范，新增脚本/工具时需同步更新根目录 README.md。新文件: ${NEW_LIST}。请更新 README.md 中的相关说明。\"}"
    exit 0
fi

exit 0
