#!/bin/bash
# PreToolUse hook: Check if compaction occurred and inject CLAUDE.md reminder
# IMPORTANT: Never interrupt Task (agent delegation) with an approval prompt to avoid recursion.

CLAUDE_DIR=".claude"
COMPACT_FLAG="$CLAUDE_DIR/.compacted"
DEBUG_LOG="$CLAUDE_DIR/hook-debug.log"
JQ_BIN="${JQ_BIN:-jq}"

# Read hook input (JSON) from stdin if present
HOOK_INPUT="$(cat 2>/dev/null || true)"
TOOL_NAME=""
if command -v "$JQ_BIN" >/dev/null 2>&1; then
  TOOL_NAME="$(printf '%s' "$HOOK_INPUT" | "$JQ_BIN" -r '.tool_name // empty' 2>/dev/null || true)"
else
  # Fallback: best-effort grep
  TOOL_NAME="$(printf '%s' "$HOOK_INPUT" | sed -n 's/.*\"tool_name\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p' | head -n1)"
fi
 
# Never interrupt Task (agent delegation) to avoid recursion
if [[ "$TOOL_NAME" == "Task" ]]; then
  echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
  exit 0
fi
 
# For non-Task tools, show compaction reminder once
if [[ -f "$COMPACT_FLAG" ]]; then
  if rm "$COMPACT_FLAG" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] CLAUDE.md reminder triggered via PreToolUse hook" >> "$DEBUG_LOG"
    cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"IMPORTANT: A compaction just occurred. Please read CLAUDE.md immediately to restore all project context, agent routing rules, and development guidelines before proceeding with any tool use."}}
EOF
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: Could not remove compact flag during PreToolUse" >> "$DEBUG_LOG"
    echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
  fi
else
  echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
fi
