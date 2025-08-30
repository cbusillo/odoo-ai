#!/bin/bash
# Pre-compact hook: Mark that compaction is occurring

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
LOG_FILE="$CLAUDE_DIR/compact.log"
DEBUG_LOG="$CLAUDE_DIR/hook-debug.log"

# Ensure .claude directory exists
mkdir -p "$CLAUDE_DIR"

# Debug: Log that hook was actually called
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PRE-COMPACT HOOK EXECUTED: type=$1, pwd=$(pwd), user=$(whoami)" >> "$DEBUG_LOG"

# Create log entry
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Compaction triggered (type: $1)" >> "$LOG_FILE"

# Create flag file for prompt-submit hook to detect
echo "$(date '+%Y-%m-%d %H:%M:%S'): $1 compact" > "$COMPACT_FLAG"

# Debug: Confirm flag file was created
if [[ -f "$COMPACT_FLAG" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Flag file created successfully at $COMPACT_FLAG" >> "$DEBUG_LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Failed to create flag file at $COMPACT_FLAG" >> "$DEBUG_LOG"
fi