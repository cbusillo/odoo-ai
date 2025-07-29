#!/bin/bash
# Pre-compact hook: Mark that compaction is occurring

CLAUDE_DIR="$CLAUDE_PROJECT_DIR/.claude"
COMPACT_FLAG="$CLAUDE_DIR/.compacted"
LOG_FILE="$CLAUDE_DIR/compact.log"

# Ensure .claude directory exists
mkdir -p "$CLAUDE_DIR"

# Create log entry
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Compaction triggered (type: $1)" >> "$LOG_FILE"

# Create flag file for prompt-submit hook to detect
echo "$(date '+%Y-%m-%d %H:%M:%S'): $1 compact" > "$COMPACT_FLAG"