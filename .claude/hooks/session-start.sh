#!/bin/sh
# SessionStart hook: Check if compaction occurred and inject CLAUDE.md reminder
# Also clears any stale agent stack files to prevent recursion issues

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Use absolute paths based on script location
CLAUDE_DIR="$PROJECT_DIR/.claude"
COMPACT_FLAG="$CLAUDE_DIR/.compacted"
DEBUG_LOG="$CLAUDE_DIR/hook-debug.log"
STACK_DIR="$PROJECT_DIR/tmp/data"

# Initialize recursion correlation environment variables
export CLAUDE_CURRENT_AGENT="PM"
export CLAUDE_DELEGATION_CHAIN="PM"
export CLAUDE_SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%s)}"

# Clear any old stack files (legacy cleanup)
if [ -d "$STACK_DIR" ]; then
    find "$STACK_DIR" -name "agent_stack_*.json" -type f -delete 2>/dev/null
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SessionStart: Initialized correlation vars, cleared old stack files" >> "$DEBUG_LOG"
fi

# Check if compaction flag exists
if [ -f "$COMPACT_FLAG" ]; then
    # Remove flag to prevent duplicate reminders
    if rm "$COMPACT_FLAG" 2>/dev/null; then
        # Log the trigger
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CLAUDE.md reminder triggered via SessionStart hook" >> "$DEBUG_LOG"
        
        # Return proper hook output format for SessionStart
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "IMPORTANT: A compaction just occurred. Please read CLAUDE.md immediately to restore all project context, agent routing rules, and development guidelines before proceeding with any tasks."
  }
}
EOF
    else
        # Log error but don't break session start
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: Could not remove compact flag during SessionStart" >> "$DEBUG_LOG"
        echo '{"status": "error"}'
    fi
else
    # No compaction flag - normal session start
    echo '{"status": "ok"}'
fi