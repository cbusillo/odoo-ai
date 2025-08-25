#!/usr/bin/env python3
"""
Prevent recursive Task() calls between agents to avoid heap exhaustion.
Tracks the agent call stack and prevents agents from calling themselves.
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

        # Only check Task tool calls (subagent invocations)
        if hook_input.get("tool_name") != "Task":
            # Not a Task call, allow it
            sys.exit(0)

        # Get the subagent being called
        tool_input = hook_input.get("tool_input", {})
        target_agent = tool_input.get("subagent_type", "")

        if not target_agent:
            # No subagent specified, allow it
            sys.exit(0)

        # Get current call stack
        stack = get_current_stack()

        # Check if this agent is already in the stack (recursion)
        if target_agent in stack:
            # RECURSION DETECTED!
            output = {
                "continue": False,
                "stopReason": f"RECURSION PREVENTED: {target_agent} agent is already active in the call stack",
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Preventing recursive call to {target_agent} agent. Call stack: {' → '.join(stack)} → {target_agent} (blocked)",
                },
            }
            print(json.dumps(output))
            sys.exit(2)  # Exit code 2 blocks the tool call

        # Check stack depth to prevent deep chains
        MAX_DEPTH = 5
        if len(stack) >= MAX_DEPTH:
            output = {
                "continue": False,
                "stopReason": f"MAX DEPTH REACHED: Agent call stack depth limit ({MAX_DEPTH}) exceeded",
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Maximum agent delegation depth ({MAX_DEPTH}) reached. Call stack: {' → '.join(stack)}",
                },
            }
            print(json.dumps(output))
            sys.exit(2)

        # No recursion detected, add to stack for tracking
        # Note: We'll need a PostToolUse hook to remove from stack
        stack.append(target_agent)
        save_stack(stack)

        # Allow the call
        sys.exit(0)

    except Exception as e:
        # On error, allow the call but log the issue
        print(json.dumps({"error": str(e), "message": "Hook error - allowing call to proceed"}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
