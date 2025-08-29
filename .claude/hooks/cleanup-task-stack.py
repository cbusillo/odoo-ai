#!/usr/bin/env python3
"""
Clean up the agent call stack after a Task completes.
This removes the agent from the stack when it finishes.
"""

import json
import sys
from pathlib import Path
import os
import hashlib
from datetime import datetime

def _stack_file() -> Path:
    """
    Use a per-project stack file in the project's tmp/data/ directory.
    This keeps temp files within the project and they get cleaned automatically.
    """
    proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("PWD") or os.getcwd()
    
    # Use project's tmp/data/ directory for temporary files
    stack_dir = Path(proj) / "tmp" / "data"
    stack_dir.mkdir(parents=True, exist_ok=True)
    
    # Create unique stack file for this session/project
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    h = hashlib.sha256(f"{proj}_{session_id}".encode("utf-8")).hexdigest()[:12]
    return stack_dir / f"agent_stack_{h}.json"


def get_current_stack():
    """Get the current agent call stack."""
    stack_path = _stack_file()
    if stack_path.exists():
        try:
            with open(stack_path, "r") as f:
                data = json.load(f)
                # ensure list of strings
                if isinstance(data, list):
                    return [str(x) for x in data]
                return []
        except:
            return []
    return []


def save_stack(stack):
    """Save the agent call stack."""
    stack_path = _stack_file()
    with open(stack_path, "w") as f:
        json.dump(stack, f)
    try:
        dbg = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".claude" / "hook-debug.log"
        dbg.parent.mkdir(parents=True, exist_ok=True)
        with open(dbg, "a") as lf:
            lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] cleanup: saved stack -> {stack} (path={stack_path})\n")
    except Exception:
        pass


def main():
    try:
        # Read the hook input from stdin
        hook_input = json.load(sys.stdin)
        dbg_path = None
        try:
            dbg_path = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".claude" / "hook-debug.log"
            dbg_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            dbg_path = None

        # Only process Task tool completions
        tool_name = hook_input.get("tool_name")
        if tool_name != "Task":
            try:
                if dbg_path:
                    with open(dbg_path, "a") as lf:
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] cleanup: skip non-Task tool={tool_name}\n")
            except Exception:
                pass
            sys.exit(0)

        # Get the subagent that just completed
        tool_input = hook_input.get("tool_input", {}) or {}
        completed_agent = tool_input.get("subagent_type") or tool_input.get("subagent") or ""

        # Get current stack
        stack = get_current_stack()

        if completed_agent and completed_agent in stack:
            # Remove the last occurrence of this agent from the stack
            # Remove from the end (most recent)
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == completed_agent:
                    stack.pop(i)
                    break
        elif stack:
            # Fallback: if no subagent_type but stack exists, pop the most recent
            # This prevents stack from growing indefinitely due to missing metadata
            # Also handle error cases where Task was blocked
            if hook_input.get("tool_result", {}).get("error"):
                # Task was blocked or errored, pop from stack anyway
                if stack:
                    stack.pop()
        
        # Save updated stack (even if empty)
        save_stack(stack)
        try:
            if dbg_path:
                with open(dbg_path, "a") as lf:
                    lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] cleanup: post-tool stack -> {stack} (completed_agent={completed_agent})\n")
        except Exception:
            pass

        # Always allow PostToolUse to continue
        sys.exit(0)

    except Exception as e:
        # On error, just continue
        try:
            dbg = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".claude" / "hook-debug.log"
            dbg.parent.mkdir(parents=True, exist_ok=True)
            with open(dbg, "a") as lf:
                lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] cleanup: error -> {e}\n")
        except Exception:
            pass
        print(json.dumps({"error": str(e), "message": "Cleanup hook error - continuing"}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
