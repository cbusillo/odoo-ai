#!/usr/bin/env python3
"""
Intercept and rewrite outdated model names in tool calls.
Replaces gpt-4o with gpt-5 since gpt-4o is no longer available.
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def log_rewrite(message):
    """Log rewrites for debugging."""
    try:
        proj_dir = Path.home() / "Developer" / "odoo-ai"
        log_path = proj_dir / ".claude" / "model-rewrite.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(log_path, "a") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except Exception:
        pass


def rewrite_model_in_value(value):
    """Recursively rewrite model names in any data structure."""
    if isinstance(value, str):
        # Replace various outdated model names
        replacements = {
            "gpt-4o": "gpt-5",
            "gpt-4o-mini": "gpt-5",
            "gpt-4-turbo": "gpt-5",
            "gpt-4": "gpt-5",
            "o1-preview": "gpt-5",
            "o1-mini": "gpt-5",
            "o1": "gpt-5",
        }
        for old, new in replacements.items():
            if old in value:
                log_rewrite(f"Replacing '{old}' with '{new}' in string value")
                value = value.replace(old, new)
        return value
    elif isinstance(value, dict):
        return {k: rewrite_model_in_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [rewrite_model_in_value(item) for item in value]
    else:
        return value


def main():
    try:
        # Read hook input
        hook_input = json.load(sys.stdin)

        tool_name = hook_input.get("tool_name", "")

        # Only process Codex and GPT-related tool calls
        relevant_tools = [
            "mcp__gpt-codex__codex",
            "mcp__gpt-codex__codex-reply",
            "mcp__gpt-codex__codex-get-response",
            "Task",  # Also check Task delegations to GPT
        ]

        if tool_name not in relevant_tools:
            # Pass through unchanged
            output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
            print(json.dumps(output))
            return

        # Get the tool input/params
        tool_input = hook_input.get("tool_input") or hook_input.get("params") or {}
        original_input = json.dumps(tool_input)

        # Special handling for Task delegations
        if tool_name == "Task":
            # Check if it's delegating to GPT with a model specified
            prompt = tool_input.get("prompt", "")
            if "gpt-4o" in prompt or "model=" in prompt:
                tool_input["prompt"] = rewrite_model_in_value(prompt)
                log_rewrite(f"Rewrote model in Task prompt for GPT delegation")
        else:
            # For Codex tools, check for model parameter
            if "model" in tool_input:
                old_model = tool_input["model"]
                tool_input["model"] = rewrite_model_in_value(old_model)
                if old_model != tool_input["model"]:
                    log_rewrite(f"Rewrote model parameter: {old_model} -> {tool_input['model']}")

            # Also check config overrides
            if "config" in tool_input:
                tool_input["config"] = rewrite_model_in_value(tool_input["config"])

        # Check if we made any changes
        if json.dumps(tool_input) != original_input:
            log_rewrite(f"Modified {tool_name} call parameters")

            # Return the modified input
            output = {
                "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "modifiedToolInput": tool_input}
            }
        else:
            # No changes needed
            output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}

        print(json.dumps(output))

    except Exception as e:
        log_rewrite(f"ERROR: {e}")
        # Allow on error
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
        print(json.dumps(output))


if __name__ == "__main__":
    main()
