#!/usr/bin/env python3
"""
Clean up the agent call stack after a Task completes.
This removes the agent from the stack when it finishes.
"""

import json
import sys
from pathlib import Path

# File to track the current agent call stack
STACK_FILE = Path("/tmp/claude_agent_stack.json")


def get_current_stack():
    """Get the current agent call stack."""
    if STACK_FILE.exists():
        try:
            with open(STACK_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []


def save_stack(stack):
    """Save the agent call stack."""
    with open(STACK_FILE, "w") as f:
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

        if not completed_agent:
            sys.exit(0)

        # Get current stack and remove the completed agent
        stack = get_current_stack()

        # Remove the last occurrence of this agent from the stack
        if completed_agent in stack:
            # Remove from the end (most recent)
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == completed_agent:
                    stack.pop(i)
                    break
            save_stack(stack)

        # Always allow PostToolUse to continue
        sys.exit(0)

    except Exception as e:
        # On error, just continue
        print(json.dumps({"error": str(e), "message": "Cleanup hook error - continuing"}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
