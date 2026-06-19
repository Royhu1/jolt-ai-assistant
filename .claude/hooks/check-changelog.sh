#!/bin/bash
# Stop hook: 强制每次对话完成代码任务后更新 logs/changelog_*.md
#
# 逻辑：
# 1. 如果 stop_hook_active=true，说明已经触发过一次，放行（防无限循环）
# 2. 如果 src/jolt_toolkit/ 或根目录有 .py 文件被修改（git diff），
#    但 logs/changelog_*.md 没有被修改，则 block 并提醒更新
# 3. 其他情况放行

INPUT=$(cat)

# 防止无限循环：如果已经是 stop_hook 触发的续写，直接放行
# 用 grep 代替 jq（Windows 环境可能没有 jq）
if echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

# 检查是否有代码文件被修改（staged + unstaged）
CODE_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep -E '\.(py|json)$' | grep -v '__pycache__' | head -1)
CODE_STAGED=$(git diff --cached --name-only 2>/dev/null | grep -E '\.(py|json)$' | grep -v '__pycache__' | head -1)

# 如果没有代码修改，放行
if [ -z "$CODE_CHANGED" ] && [ -z "$CODE_STAGED" ]; then
    exit 0
fi

# 检查 changelog 是否已被修改（canonical: changelogs/；兼容旧 logs/ 与根 changelog.md）
CHANGELOG_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep -E '(^changelogs/changelog_|^logs/changelog_|^changelog\.md$)')
CHANGELOG_STAGED=$(git diff --cached --name-only 2>/dev/null | grep -E '(^changelogs/changelog_|^logs/changelog_|^changelog\.md$)')

if [ -z "$CHANGELOG_CHANGED" ] && [ -z "$CHANGELOG_STAGED" ]; then
    echo '{"decision": "block", "reason": "[doc-hook] 检测到代码文件已修改但 logs/changelog 未更新。根据 CLAUDE.md 文档维护规范，每次对话结束前必须更新 logs/changelog_YYYYMMDD_YYYYMMDD.md（Q&A 格式记录本次任务和结果摘要）。请立即更新当周的 changelog 文件。"}'
    exit 0
fi

# changelog 已更新，放行
exit 0
