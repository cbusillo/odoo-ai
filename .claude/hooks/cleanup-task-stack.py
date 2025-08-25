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

def _stack_file() -> Path:
    """
    Use a per-project stack file so different projects don't share state.
    Falls back to a global file if project dir isn't provided.
    """
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        h = hashlib.sha256(proj.encode("utf-8")).hexdigest()[:12]
        return Path(f"/tmp/claude_agent_stack_{h}.json")
    return Path("/tmp/claude_agent_stack.json")


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


def main():
    try:
        # Read the hook input from stdin
        hook_input = json.load(sys.stdin)

        # Only process Task tool completions
        if hook_input.get("tool_name") != "Task":
            sys.exit(0)

        # Get the subagent that just completed
        tool_input = hook_input.get("tool_input", {})
        completed_agent = tool_input.get("subagent_type", "")

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
            stack.pop()
        
        # Save updated stack (even if empty)
        save_stack(stack)

        # Always allow PostToolUse to continue
        sys.exit(0)

    except Exception as e:
        # On error, just continue
        print(json.dumps({"error": str(e), "message": "Cleanup hook error - continuing"}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
