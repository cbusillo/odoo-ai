#!/usr/bin/env python3
"""
File-based recursion prevention with durable state tracking.
Fixes the environment variable persistence issue identified by GPT analysis.
"""

import json
import sys
import os
import time
import fcntl
from datetime import datetime
from pathlib import Path


# Configuration
MAX_DEPTH = 2
STALE_TIMEOUT_MINUTES = 5
CIRCUIT_BREAKER_WINDOW = 30  # seconds
CIRCUIT_BREAKER_THRESHOLD = 5  # denials

# Agent normalization mapping
AGENT_ALIASES = {
    "pm": "planner",
    "playwrite": "playwright", 
    "programme-manager": "planner",
    "program-manager": "planner"
}

VALID_AGENTS = [
    'archer', 'scout', 'inspector', 'qc', 'dock', 'shopkeeper', 'owl', 
    'phoenix', 'flash', 'debugger', 'planner', 'refactor', 'playwright',
    'odoo-engineer', 'anthropic-engineer', 'gpt', 'doc'
]


def normalize_agent_slug(name):
    """Normalize agent name to canonical slug."""
    if not name:
        return "planner"  # default
    
    # Strip emojis and normalize
    base = name.strip().lower()
    base = base.encode("ascii", "ignore").decode()
    
    # Apply aliases
    base = AGENT_ALIASES.get(base, base)
    
    # Validate against known agents
    if base not in VALID_AGENTS:
        return "planner"  # fallback for unknown agents
    
    return base


def get_stack_file():
    """Get path to the session-specific stack file."""
    proj_dir = os.environ.get("CLAUDE_PROJECT_DIR", "/Users/cbusillo/Developer/odoo-ai")
    stack_dir = Path(proj_dir) / ".claude" / "agent-stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    return stack_dir / f"{session_id}.json"


def load_stack():
    """Load the agent delegation stack with file locking."""
    stack_file = get_stack_file()
    
    if not stack_file.exists():
        return {
            "session_id": os.environ.get("CLAUDE_SESSION_ID", "default"),
            "stack": [],
            "seen": [],
            "last_updated": time.time(),
            "denials": []
        }
    
    try:
        with open(stack_file, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
            data = json.load(f)
            
            # Check for stale stack
            if time.time() - data.get("last_updated", 0) > STALE_TIMEOUT_MINUTES * 60:
                log_decision("Stack is stale, resetting")
                return {
                    "session_id": data.get("session_id", "default"),
                    "stack": [],
                    "seen": [],
                    "last_updated": time.time(),
                    "denials": []
                }
            
            return data
    except Exception as e:
        log_decision(f"Error loading stack: {e}, creating new")
        return {
            "session_id": os.environ.get("CLAUDE_SESSION_ID", "default"),
            "stack": [],
            "seen": [],
            "last_updated": time.time(),
            "denials": []
        }


def save_stack(data):
    """Save the agent delegation stack with file locking."""
    stack_file = get_stack_file()
    data["last_updated"] = time.time()
    
    try:
        with open(stack_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
            json.dump(data, f, indent=2)
        log_decision(f"Stack saved: {data['stack']}")
    except Exception as e:
        log_decision(f"Error saving stack: {e}")


def check_circuit_breaker(data, target_agent):
    """Check if circuit breaker should trip for repeated denials."""
    now = time.time()
    
    # Clean old denials outside the window
    data["denials"] = [
        d for d in data.get("denials", [])
        if now - d["timestamp"] < CIRCUIT_BREAKER_WINDOW
    ]
    
    # Count recent denials for this target
    recent_denials = [
        d for d in data["denials"]
        if d["target"] == target_agent
    ]
    
    if len(recent_denials) >= CIRCUIT_BREAKER_THRESHOLD:
        return True, f"Circuit breaker: {len(recent_denials)} denials for {target_agent} in {CIRCUIT_BREAKER_WINDOW}s"
    
    return False, ""


def log_decision(message):
    """Log decisions for debugging."""
    try:
        proj_dir = os.environ.get("CLAUDE_PROJECT_DIR", "/Users/cbusillo/Developer/odoo-ai")
        log_path = Path(proj_dir) / ".claude" / "recursion-file.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "a") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except Exception:
        pass


def main():
    try:
        # Read hook input
        hook_input = json.load(sys.stdin)
        
        # Only process Task tool calls (cover GPT delegation later)
        tool_name = hook_input.get("tool_name")
        if tool_name != "Task":
            log_decision(f"Allowing non-Task tool: {tool_name}")
            sys.exit(0)
        
        # Get target agent
        tool_input = hook_input.get("tool_input", {}) or {}
        raw_target = tool_input.get("subagent_type", "").strip()
        
        if not raw_target:
            log_decision("Allowing Task with no subagent_type")
            sys.exit(0)
        
        target_agent = normalize_agent_slug(raw_target)
        log_decision(f"Target agent: {raw_target} → {target_agent}")
        
        # Load current stack
        data = load_stack()
        current_agent = data["stack"][-1] if data["stack"] else "planner"
        
        log_decision(f"Current stack: {data['stack']} (current: {current_agent})")
        
        # Check circuit breaker first
        circuit_tripped, circuit_reason = check_circuit_breaker(data, target_agent)
        if circuit_tripped:
            log_decision(f"BLOCKING {circuit_reason}")
            
            guidance = f"""
CIRCUIT BREAKER TRIPPED: {circuit_reason}

The system has blocked repeated attempts to delegate to {target_agent}.
This suggests an underlying issue that needs manual intervention.

ACTIONS:
- Handle the current task directly with available tools
- Do not retry delegation to {target_agent}  
- Consider breaking the task into smaller pieces

Circuit breaker will reset automatically in {CIRCUIT_BREAKER_WINDOW} seconds.
"""
            
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": guidance
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Check recursion rules
        blocked = False
        block_reason = ""
        
        # Rule 1: Self-call
        if current_agent == target_agent:
            blocked = True
            block_reason = f"SELF-CALL: {current_agent} cannot call itself"
        
        # Rule 2: Cycle detection
        elif target_agent in data["stack"]:
            blocked = True
            block_reason = f"CYCLE: {target_agent} already in chain {' → '.join(data['stack'])}"
        
        # Rule 3: Depth limit
        elif len(data["stack"]) >= MAX_DEPTH:
            blocked = True
            block_reason = f"DEPTH LIMIT: Stack depth {len(data['stack'])} >= {MAX_DEPTH}"
        
        if blocked:
            # Record the denial
            data["denials"].append({
                "target": target_agent,
                "reason": block_reason,
                "timestamp": time.time()
            })
            save_stack(data)
            
            log_decision(f"BLOCKING {block_reason}")
            
            guidance = f"""
DELEGATION BLOCKED: {block_reason}

Current delegation chain: {' → '.join(data['stack'] + [target_agent])}

RECOMMENDED ACTIONS:
- Use direct tools: Edit, Write, Read, Grep, Bash, MCP tools
- Complete the task within your domain expertise
- Do not attempt to delegate to {target_agent}

The recursion prevention system is protecting against infinite loops.
"""
            
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse", 
                    "permissionDecision": "deny",
                    "permissionDecisionReason": guidance
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Allow the delegation - push to stack
        data["stack"].append(target_agent)
        if target_agent not in data["seen"]:
            data["seen"].append(target_agent)
        
        save_stack(data)
        
        log_decision(f"ALLOWING delegation: {current_agent} → {target_agent}")
        log_decision(f"New stack: {data['stack']}")
        
        sys.exit(0)
        
    except Exception as e:
        log_decision(f"ERROR: {e}")
        sys.exit(0)  # Allow on error to prevent blocking legitimate calls


if __name__ == "__main__":
    main()