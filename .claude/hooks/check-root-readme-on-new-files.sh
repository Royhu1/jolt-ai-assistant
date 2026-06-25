#!/bin/bash
# Stop hook: enforce updating the root README.md when new script or tool files are added
#
# Logic:
# 1. Prevent infinite loops
# 2. If there are newly added .py or .sh files (untracked or newly added),
#    but the root README.md has not been modified, then block
# 3. Only detect new files in the root directory and under src/jolt_toolkit/
#    (excluding auxiliary directories such as cache/, reports/, parameter_identify/)

INPUT=$(cat)

if echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

# Check whether any new script files have been added (new files in git diff + untracked)
NEW_FILES_DIFF=$(git diff --name-only --diff-filter=A HEAD 2>/dev/null | grep -E '^(src/jolt_toolkit/[^/]+\.py|[^/]+\.(py|sh))$' | head -1)
NEW_FILES_STAGED=$(git diff --cached --name-only --diff-filter=A 2>/dev/null | grep -E '^(src/jolt_toolkit/[^/]+\.py|[^/]+\.(py|sh))$' | head -1)
NEW_UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null | grep -E '^(src/jolt_toolkit/[^/]+\.py|[^/]+\.(py|sh))$' | head -1)

if [ -z "$NEW_FILES_DIFF" ] && [ -z "$NEW_FILES_STAGED" ] && [ -z "$NEW_UNTRACKED" ]; then
    exit 0
fi

# There are new files; check whether the root README.md has been updated
ROOT_README_CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep '^README.md$')
ROOT_README_STAGED=$(git diff --cached --name-only 2>/dev/null | grep '^README.md$')

if [ -z "$ROOT_README_CHANGED" ] && [ -z "$ROOT_README_STAGED" ]; then
    NEW_LIST="${NEW_FILES_DIFF}${NEW_FILES_STAGED}${NEW_UNTRACKED}"
    echo "{\"decision\": \"block\", \"reason\": \"[doc-hook] Detected that new script/tool files have been added but the root README.md has not been updated. According to the CLAUDE.md conventions, when adding scripts/tools you must update the root README.md at the same time. New files: ${NEW_LIST}. Please update the relevant description in README.md.\"}"
    exit 0
fi

exit 0
