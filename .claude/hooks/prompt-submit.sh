#!/bin/bash
# UserPromptSubmit hook: Check if compaction occurred and inject CLAUDE.md reminder

# Find the project root - use CLAUDE_PROJECT_DIR if set, otherwise find it
if [[ -n "$CLAUDE_PROJECT_DIR" ]]; then
    PROJECT_DIR="$CLAUDE_PROJECT_DIR"
else
    # Get the directory where this script is located and go up 2 levels
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
CLAUDE_DIR="$PROJECT_DIR/.claude"
COMPACT_FLAG="$CLAUDE_DIR/.compacted"
DEBUG_LOG="$CLAUDE_DIR/hook-debug.log"

# Check if compaction flag exists
if [[ -f "$COMPACT_FLAG" ]]; then
    # Remove flag to prevent duplicate reminders
    if rm "$COMPACT_FLAG" 2>/dev/null; then
        # Log the trigger
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CLAUDE.md reminder triggered via UserPromptSubmit hook" >> "$DEBUG_LOG"
        
        # Return proper hook output format for Claude Code August 2025
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "IMPORTANT: A compaction just occurred. Please read CLAUDE.md immediately to restore all project context, agent routing rules, and development guidelines before proceeding with any tasks."
  }
}
EOF
    else
        # Log error but don't break the prompt flow  
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: Could not remove compact flag" >> "$DEBUG_LOG"
        echo '{"status": "error"}' 
    fi
else
    # No compaction flag - normal operation
    echo '{"status": "ok"}'
fi