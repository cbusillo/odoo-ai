# 🚨 Recursion Prevention - Agent Guidelines

## CRITICAL: Never Call Yourself

**Agents MUST NOT delegate to themselves** - This crashes Claude Code!

## Core Principle: Own Your Domain

Handle tasks within your expertise directly. Use your tools, not Task() to yourself.

## When You See "Preventing recursion"

The hook blocked a self-call that would crash the system. You MUST:

### DO:

- Use Edit/Write/MultiEdit for file changes
- Use Read/Grep/Bash for analysis
- Complete the work with your available tools

### DON'T:

- Call Task() with your own agent type
- Switch to a different agent
- Abandon the current task

## Simple Examples

❌ **Wrong:** `Task(subagent_type="doc")` from within doc agent  
✅ **Right:** `Edit(file_path="README.md", old_string="...", new_string="...")`

❌ **Wrong:** `Task(subagent_type="scout")` from within scout agent  
✅ **Right:** Use your testing tools directly

## Exception: Cross-Agent Delegation

These patterns are healthy:

- `archer → odoo-engineer` (Research → Implementation)
- `debugger → dock` (Error analysis → Container fixes)
- `planner → specialists` (Planning → Execution)

## Enhanced Protection (Aug 2025)

**New safeguards to prevent crashes:**

- ✅ Blocks ALL self-calls (not just immediate)
- ✅ Stack depth limited to 2 levels (was 3)
- ✅ Auto-clears stale stacks after 5 minutes
- ✅ Session start resets all stacks
- ✅ Better cleanup on blocked tasks

## Hook Status

Temporary solution until Anthropic ships built-in recursion protection (Issues #6468, #4277)