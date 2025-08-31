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
import fcntl

def _stack_file() -> Path:
    """
    Use a per-project stack file in the project's tmp/data/ directory.
    This keeps temp files within the project and they get cleaned automatically.
    """
    # ALWAYS use CLAUDE_PROJECT_DIR if available
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if not proj:
        # Find project root by looking for .claude directory upwards
        current = Path(__file__).parent.parent.parent  # hooks -> .claude -> project
        proj = str(current.resolve())
    
    # Use project's tmp/data/ directory for temporary files
    stack_dir = Path(proj) / "tmp" / "data"
    stack_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean up old stack files (older than 5 minutes for better recovery)
    try:
        now = time.time()
        for old_file in stack_dir.glob("agent_stack_*.json"):
            if now - old_file.stat().st_mtime > 300:  # 5 minutes (was 1 hour)
                old_file.unlink()
    except Exception:
        pass  # Continue even if cleanup fails
    
    # Create unique stack file for this session/project
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    h = hashlib.sha256(f"{proj}_{session_id}".encode("utf-8")).hexdigest()[:12]
    return stack_dir / f"agent_stack_{h}.json"


def get_current_stack():
    """Get the current agent call stack with file locking."""
    stack_path = _stack_file()
    if stack_path.exists():
        try:
            # Reset stale stacks older than 5 minutes to avoid persistent lockouts
            # This handles cases where cleanup hooks don't run (e.g., blocked tasks)
            if time.time() - stack_path.stat().st_mtime > 5 * 60:  # 5 minutes (was 10)
                return []
            with open(stack_path, "r") as f:
                # Use file locking to prevent concurrent access issues
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                data = json.load(f)
                # ensure list of strings
                if isinstance(data, list):
                    return [str(x) for x in data]
                return []
        except:
            return []
    return []


def save_stack(stack):
    """Save the agent call stack with file locking."""
    stack_path = _stack_file()
    with open(stack_path, "w") as f:
        # Use exclusive lock for writing to prevent race conditions
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        json.dump(stack, f)
    # Touch file mtime for staleness checks
    try:
        stack_path.touch(exist_ok=True)
    except Exception:
        pass
    # Best-effort debug log
    try:
        # Find project root safely
        proj_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if not proj_dir:
            proj_dir = str(Path(__file__).parent.parent.parent.resolve())
        dbg = Path(proj_dir) / ".claude" / "hook-debug.log"
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
            # Find project root safely
            proj_dir = os.environ.get("CLAUDE_PROJECT_DIR")
            if not proj_dir:
                proj_dir = str(Path(__file__).parent.parent.parent.resolve())
            dbg_path = Path(proj_dir) / ".claude" / "hook-debug.log"
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

        # Check if this agent is trying to call itself (ANY self-call, not just immediate)
        decision_note = ""
        # Block ANY self-call to prevent loops - agent should never call itself
        # CRITICAL: Check BEFORE adding to stack to prevent race condition
        is_self_call = target_agent in stack
        
        # ADDITIONAL PROTECTION: Also check if agent would appear more than once
        # This catches cases where concurrent calls might bypass the first check
        would_duplicate = stack.count(target_agent) > 0
        
        # ULTRA-STRICT: Block if we would have ANY duplicate at all
        # This prevents even the first self-call from succeeding
        immediate_self_call = len(stack) > 0 and stack[-1] == target_agent
        
        # IMPORTANT: Don't add to stack if we're going to block
        # This prevents stuck stacks when cleanup hooks don't run
        if is_self_call or would_duplicate or immediate_self_call:
            # RECURSION DETECTED! Block any attempt at self-delegation
            agent_count = stack.count(target_agent) + 1  # Count including this attempt
            decision_note = f"deny: self-call"
            
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
                proj_dir = os.environ.get("CLAUDE_PROJECT_DIR")
                if not proj_dir:
                    proj_dir = str(Path(__file__).parent.parent.parent.resolve())
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
                    "permissionDecisionReason": f"Preventing recursion: {target_agent} cannot call itself (appears {agent_count} times in stack). Current stack: {' → '.join(stack)}\n\nRECOMMENDED ACTION: The current {target_agent} agent should continue with direct tools instead of self-delegation. For tasks in your domain, use Edit, Write, MultiEdit, Read, Grep, etc. See docs/agent-patterns/anti-recursion-guidelines.md",
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
        MAX_DEPTH = 2  # Reduced from 3 to be more conservative
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
        # IMPORTANT: Only add if we're allowing the call
        stack.append(str(target_agent))
        save_stack(stack)
        try:
            if dbg_path:
                with open(dbg_path, "a") as lf:
                    lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: allow; push {target_agent} -> {stack} (depth: {len(stack)})\n")
        except Exception:
            pass

        # Allow the call
        sys.exit(0)

    except Exception as e:
        # On error, allow the call but log the issue
        try:
            # Find project root safely
            proj_dir = os.environ.get("CLAUDE_PROJECT_DIR")
            if not proj_dir:
                proj_dir = str(Path(__file__).parent.parent.parent.resolve())
            dbg = Path(proj_dir) / ".claude" / "hook-debug.log"
            dbg.parent.mkdir(parents=True, exist_ok=True)
            with open(dbg, "a") as lf:
                lf.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] prevent: error -> {e}\n")
        except Exception:
            pass
        print(json.dumps({"error": str(e), "message": "Hook error - allowing call to proceed"}), file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
