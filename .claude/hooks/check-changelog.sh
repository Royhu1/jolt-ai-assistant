#!/bin/bash
# Stop hook: enforce updating logs/changelog_*.md after every conversation that completes a code task
#
# Logic:
# 1. If stop_hook_active=true, it means it has already been triggered once, so allow it through (prevent infinite loops)
# 2. If a .py file under src/jolt_toolkit/ or the root directory has been modified (git diff),
#    but logs/changelog_*.md has not been modified, then block and prompt for an update
# 3. Otherwise, allow it through

INPUT=$(cat)

# Prevent infinite loops: if this is already a continuation triggered by stop_hook, allow it through directly
# Use grep instead of jq (the Windows environment may not have jq)
if echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

# Check whether any code files have been modified (staged + unstaged)
CODE_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep -E '\.(py|json)$' | grep -v '__pycache__' | head -1)
CODE_STAGED=$(git diff --cached --name-only 2>/dev/null | grep -E '\.(py|json)$' | grep -v '__pycache__' | head -1)

# If there are no code changes, allow it through
if [ -z "$CODE_CHANGED" ] && [ -z "$CODE_STAGED" ]; then
    exit 0
fi

# Check whether the changelog has been modified (canonical: changelogs/; also compatible with the old logs/ and the root changelog.md)
CHANGELOG_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep -E '(^changelogs/changelog_|^logs/changelog_|^changelog\.md$)')
CHANGELOG_STAGED=$(git diff --cached --name-only 2>/dev/null | grep -E '(^changelogs/changelog_|^logs/changelog_|^changelog\.md$)')

if [ -z "$CHANGELOG_CHANGED" ] && [ -z "$CHANGELOG_STAGED" ]; then
    echo '{"decision": "block", "reason": "[doc-hook] Detected that code files have been modified but logs/changelog has not been updated. According to the CLAUDE.md documentation-maintenance conventions, before the end of every conversation you must update logs/changelog_YYYYMMDD_YYYYMMDD.md (recording a summary of this task and its result in Q&A format). Please update the changelog file for the current week immediately."}'
    exit 0
fi

# changelog has been updated, allow it through
exit 0
