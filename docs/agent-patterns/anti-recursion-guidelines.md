# Recursion Prevention - Agent Guidelines

## Core Principle: Own Your Domain

Handle tasks within your expertise directly. Don't delegate back to yourself.

## When You See "Preventing excessive recursion"

The hook caught you trying to self-delegate. Continue with direct tools instead.

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

## Hook Status

This is a temporary solution until Anthropic ships built-in recursion protection.