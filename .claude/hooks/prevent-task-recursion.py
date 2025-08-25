#!/usr/bin/env python3
"""
Prevent recursive Task() calls between agents to avoid heap exhaustion.
Tracks the agent call stack and prevents agents from calling themselves.
"""

import json
import sys
from pathlib import Path
import os
import time
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
            # Reset stale stacks older than 2 hours to avoid permanent lockouts
            if time.time() - stack_path.stat().st_mtime > 2 * 60 * 60:
                return []
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
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Preventing recursive call to {target_agent} agent. Call stack: {' → '.join(stack)} → {target_agent} (blocked)",
                },
            }
            print(json.dumps(output))
            # Exit 0 so the platform respects the deny decision without retries
            sys.exit(0)

        # Check stack depth to prevent deep chains
        # Keep chains shallow to prevent ping-pong loops from growing
        MAX_DEPTH = 3
        if len(stack) >= MAX_DEPTH:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Maximum agent delegation depth ({MAX_DEPTH}) reached. Call stack: {' → '.join(stack)}",
                },
            }
            print(json.dumps(output))
            sys.exit(0)

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
