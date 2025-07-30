#!/bin/bash
# Post-compact hook: Check if compaction occurred and inject CLAUDE.md reminder

CLAUDE_DIR=".claude"
COMPACT_FLAG="$CLAUDE_DIR/.compacted"

# Output to stderr for claude --debug visibility
debug_log() {
    echo "[prompt-submit.sh] $1" >&2
}

# Check if compaction flag exists
if [[ -f "$COMPACT_FLAG" ]]; then
    debug_log "Compact flag detected - triggering CLAUDE.md reminder"
    
    # Remove flag to prevent duplicate reminders
    if rm "$COMPACT_FLAG" 2>/dev/null; then
        debug_log "Removed compact flag successfully"
        
        # Return additional prompt to remind Claude about CLAUDE.md
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "CRITICAL: Conversation was just compacted. You MUST immediately read CLAUDE.md in the project root to restore all project instructions, conventions, and safety rules. Do not proceed with any tasks until you've confirmed you've read and understood CLAUDE.md."
  }
}
EOF
    else
        # Log error but don't break the prompt flow  
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: Could not remove compact flag" >> "$CLAUDE_DIR/compact.log"
        debug_log "ERROR: Failed to remove compact flag - see $CLAUDE_DIR/compact.log"
    fi
else
    debug_log "No compaction detected - normal operation"
fi