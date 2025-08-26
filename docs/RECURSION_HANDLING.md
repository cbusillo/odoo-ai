# Recursion Handling - Temporary Solution

## When You See "Preventing excessive recursion"

Agents CAN call themselves once (for work decomposition), but not repeatedly.

- ✅ `refactor → refactor` (allowed once, useful for batching)
- ❌ `refactor → refactor → refactor` (blocked at depth 2)

This prevents infinite loops while allowing useful self-delegation patterns.

## DO NOT:

- Switch to a different agent
- Apply routing rules (like "5+ files → GPT")
- Abandon the current task

## DO:

- Let the current agent continue
- Use direct tools instead of delegation
- Break work into smaller chunks

## This is temporary

Anthropic is aware (GitHub issues #6468, #4277, #4182) and working on built-in recursion protection. Once that ships, we
can remove our hooks.

## Stack cleanup

If needed: `rm /tmp/claude_agent_stack_*.json`