#!/usr/bin/env python3
"""
PostToolUse hook to clean up the agent delegation stack.
Pops the agent when Task completes (success or failure).
"""

import json
import sys
import os
import time
import fcntl
from datetime import datetime
from pathlib import Path


def get_stack_file():
    """Get path to the session-specific stack file."""
    proj_dir = os.environ.get("CLAUDE_PROJECT_DIR", "/Users/cbusillo/Developer/odoo-ai")
    stack_dir = Path(proj_dir) / ".claude" / "agent-stack"
    return stack_dir / f"{os.environ.get('CLAUDE_SESSION_ID', 'default')}.json"


def load_stack():
    """Load the agent delegation stack with file locking."""
    stack_file = get_stack_file()
    
    if not stack_file.exists():
        return None
    
    try:
        with open(stack_file, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            return json.load(f)
    except Exception:
        return None


def save_stack(data):
    """Save the agent delegation stack with file locking."""
    stack_file = get_stack_file()
    data["last_updated"] = time.time()
    
    try:
        with open(stack_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(data, f, indent=2)
        log_decision(f"Stack after cleanup: {data['stack']}")
    except Exception as e:
        log_decision(f"Error saving stack: {e}")


def log_decision(message):
    """Log decisions for debugging."""
    try:
        proj_dir = os.environ.get("CLAUDE_PROJECT_DIR", "/Users/cbusillo/Developer/odoo-ai")
        log_path = Path(proj_dir) / ".claude" / "recursion-file.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] CLEANUP: {message}\n")
    except Exception:
        pass


def main():
    try:
        # Read hook input
        hook_input = json.load(sys.stdin)
        
        # Only process Task completions
        tool_name = hook_input.get("tool_name")
        if tool_name != "Task":
            log_decision(f"Ignoring non-Task completion: {tool_name}")
            sys.exit(0)
        
        # Check if the task was actually executed (not denied by PreToolUse)
        tool_result = hook_input.get("tool_result", {})
        hook_output = tool_result.get("hookSpecificOutput", {})
        
        # If task was denied by PreToolUse hook, don't pop the stack
        if hook_output.get("permissionDecision") == "deny":
            log_decision("Task was denied, not popping stack")
            sys.exit(0)
        
        # Load and update stack
        data = load_stack()
        if not data or not data.get("stack"):
            log_decision("No stack to clean up")
            sys.exit(0)
        
        # Pop the completed agent from the stack
        completed_agent = data["stack"].pop() if data["stack"] else None
        
        if completed_agent:
            log_decision(f"Popped completed agent: {completed_agent}")
            save_stack(data)
        else:
            log_decision("No agent to pop from empty stack")
        
        sys.exit(0)
        
    except Exception as e:
        log_decision(f"ERROR: {e}")
        sys.exit(0)  # Continue even on error


if __name__ == "__main__":
    main()