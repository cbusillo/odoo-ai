#!/bin/bash
# PreToolUse hook: Check if compaction occurred and inject CLAUDE.md reminder

CLAUDE_DIR=".claude"
COMPACT_FLAG="$CLAUDE_DIR/.compacted"
DEBUG_LOG="$CLAUDE_DIR/hook-debug.log"

# Check if compaction flag exists
if [[ -f "$COMPACT_FLAG" ]]; then
    # Remove flag to prevent duplicate reminders
    if rm "$COMPACT_FLAG" 2>/dev/null; then
        # Log the trigger
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CLAUDE.md reminder triggered via PreToolUse hook" >> "$DEBUG_LOG"
        
        # Return proper hook output format for PreToolUse
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "IMPORTANT: A compaction just occurred. Please read CLAUDE.md immediately to restore all project context, agent routing rules, and development guidelines before proceeding with any tool use."
  }
}
EOF
    else
        # Log error but allow tool use to continue
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: Could not remove compact flag during PreToolUse" >> "$DEBUG_LOG"
        echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
    fi
else
    # No compaction flag - allow normal tool use
    echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}'
fi