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
    
    # Clean up old stack files (older than 1 hour)
    try:
        now = time.time()
        for old_file in stack_dir.glob("agent_stack_*.json"):
            if now - old_file.stat().st_mtime > 3600:  # 1 hour
                old_file.unlink()
    except Exception:
        pass  # Continue even if cleanup fails
    
    # Create unique stack file for this session/project
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    h = hashlib.sha256(f"{proj}_{session_id}".encode("utf-8")).hexdigest()[:12]
    return stack_dir / f"agent_stack_{h}.json"


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
    # Touch file mtime for staleness checks
    try:
        stack_path.touch(exist_ok=True)
    except Exception:
        pass
    # Best-effort debug log
    try:
        dbg = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".claude" / "hook-debug.log"
        dbg.parent.mkdir(parents=True, exist_ok=True)
        with open(dbg, "a") as lf:
            lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: saved stack -> {stack} (path={stack_path})\n")
    except Exception:
        pass


def main():
    try:
        # Read the hook input from stdin
        hook_input = json.load(sys.stdin)
        # Prepare debug log
        dbg_path = None
        try:
            dbg_path = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".claude" / "hook-debug.log"
            dbg_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            dbg_path = None

        # Only check Task tool calls (subagent invocations)
        tool_name = hook_input.get("tool_name")
        if tool_name != "Task":
            # Not a Task call, allow it
            try:
                if dbg_path:
                    with open(dbg_path, "a") as lf:
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: skip non-Task tool={tool_name}\n")
            except Exception:
                pass
            sys.exit(0)

        # Get the subagent being called
        tool_input = hook_input.get("tool_input", {}) or {}
        target_agent = tool_input.get("subagent_type") or tool_input.get("subagent") or ""

        if not target_agent or not str(target_agent).strip():
            # No subagent specified, allow it
            try:
                if dbg_path:
                    with open(dbg_path, "a") as lf:
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: allow (no subagent) tool_input_keys={list(tool_input.keys())}\n")
            except Exception:
                pass
            sys.exit(0)

        # Get current call stack
        stack = get_current_stack()

        # Check if this agent is already in the stack too many times
        decision_note = ""
        MAX_SELF_CALLS = 1  # Allow agent to call itself once, block on second attempt
        agent_count = stack.count(target_agent)
        
        if agent_count >= MAX_SELF_CALLS:
            # EXCESSIVE RECURSION DETECTED! Signal to continue with current agent instead of re-routing
            decision_note = f"deny: recursion (depth {agent_count})"
            
            # Create event signal file for orchestrator to detect
            try:
                event_data = {
                    "type": "recursion_blocked",
                    "from_agent": target_agent,
                    "to_agent": target_agent,
                    "stack": stack,
                    "time": datetime.now().isoformat(),
                    "action": "continue_current_agent"
                }
                proj_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
                event_dir = Path(proj_dir) / "tmp" / "data"
                event_dir.mkdir(parents=True, exist_ok=True)
                event_file = event_dir / "recursion_event.json"
                with open(event_file, "w") as f:
                    json.dump(event_data, f)
            except Exception:
                pass  # Continue even if signal file creation fails
            
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Preventing excessive recursion of {target_agent} agent (appears {agent_count} times in stack). Agent should continue locally. Call stack: {' → '.join(stack)} → {target_agent} (blocked)\n\nRECOMMENDED ACTION: Recall the same agent with anti-recursion instructions:\nTask(\n    description=\"[original task]\",\n    prompt=\"[original request]\n\nIMPORTANT: Do NOT call Task() with subagent_type='{target_agent}'. You can delegate to other agents and use all other tools. For tasks in your domain, use direct tools (Edit, Write, MultiEdit). See docs/agent-patterns/anti-recursion-guidelines.md\",\n    subagent_type=\"{target_agent}\"\n)",
                },
            }
            print(json.dumps(output))
            # Exit 95 - special code meaning "blocked, continue current agent, don't re-route"
            try:
                if dbg_path:
                    with open(dbg_path, "a") as lf:
                        tool_prompt = tool_input.get("prompt", "")[:100] + "..." if len(tool_input.get("prompt", "")) > 100 else tool_input.get("prompt", "")
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: {decision_note}; env(PWD={os.environ.get('PWD')}, CLAUDE_PROJECT_DIR={os.environ.get('CLAUDE_PROJECT_DIR')}) stack={stack} target={target_agent} signal=continue_current\n")
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: BLOCKED SELF-CALL: {target_agent} attempted recursive call (prompt: {tool_prompt})\n")
            except Exception:
                pass
            sys.exit(95)  # Special exit code for "continue current agent"

        # Check stack depth to prevent deep chains
        # Keep chains shallow to prevent ping-pong loops from growing
        MAX_DEPTH = 3
        if len(stack) >= MAX_DEPTH:
            decision_note = "deny: max-depth"
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Maximum agent delegation depth ({MAX_DEPTH}) reached. Call stack: {' → '.join(stack)}",
                },
            }
            print(json.dumps(output))
            try:
                if dbg_path:
                    with open(dbg_path, "a") as lf:
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: {decision_note}; stack={stack}\n")
            except Exception:
                pass
            sys.exit(0)

        # No recursion detected, add to stack for tracking
        # Note: We'll need a PostToolUse hook to remove from stack
        stack.append(str(target_agent))
        save_stack(stack)
        try:
            if dbg_path:
                # Get basic process info for correlation with crashes
                try:
                    # Simple approach: check if we can get basic OS info
                    pid = os.getpid()
                    memory_info = f"pid: {pid}"
                except:
                    memory_info = "pid: unknown"
                
                # Calculate what the stack will look like after we add this agent
                new_stack = stack + [target_agent]
                new_agent_count = new_stack.count(target_agent)
                
                with open(dbg_path, "a") as lf:
                    lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: allow; push {target_agent} -> {new_stack} (self-call depth: {new_agent_count}, total depth: {len(new_stack)}, {memory_info})\n")
                    # Log tool input details for self-calls
                    if agent_count > 0:
                        tool_prompt = tool_input.get("prompt", "")[:200] + "..." if len(tool_input.get("prompt", "")) > 200 else tool_input.get("prompt", "")
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: SELF-CALL DETECTED: {target_agent} calling itself ({memory_info})\n")
                        lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: SELF-CALL PROMPT: {tool_prompt}\n")
        except Exception:
            pass

        # Allow the call
        sys.exit(0)

    except Exception as e:
        # On error, allow the call but log the issue
        try:
            dbg = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".claude" / "hook-debug.log"
            dbg.parent.mkdir(parents=True, exist_ok=True)
            with open(dbg, "a") as lf:
                lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: error -> {e}\n")
        except Exception:
            pass
        print(json.dumps({"error": str(e), "message": "Hook error - allowing call to proceed"}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
