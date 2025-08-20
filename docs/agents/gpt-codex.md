# 🤖 Codex - Research & Implementation Agent

**Audience**: This agent is called by the main assistant using Task(). Users should NOT call MCP tools directly.

## Purpose

Codex is a powerful delegation agent for:

- Complex multi-step research and implementation
- Tasks requiring web access and current information
- Large-scale code analysis and refactoring
- When uncertainty needs verification with web search
- Tasks that would consume significant context

## MCP References

- Basic usage and examples: [usage.md](../codex/usage.md)
- Session management essentials: [reference.md#session-management](../codex/reference.md#session-management)
- Sandbox modes overview: [reference.md#sandbox-modes](../codex/reference.md#sandbox-modes)
- Model selection guidance: [reference.md#model-selection](../codex/reference.md#model-selection)
- Advanced configuration: [advanced.md](../codex/advanced.md)
- Common issues and troubleshooting: [reference.md#common-issues](../codex/reference.md#common-issues)

## Sandbox Mode Selection

See: [reference.md#sandbox-modes](../codex/reference.md#sandbox-modes)

## When to Delegate to Codex

### ALWAYS Delegate:

- **Web Research**: "Find the best way to...", "What's the latest..."
- **Large Tasks**: Involving 5+ files or complex multi-step processes
- **Verification**: When you're uncertain about facts or best practices
- **Current Information**: Anything requiring up-to-date knowledge
- **Complex Analysis**: Deep code review, architecture analysis

### Example Delegation Patterns

#### Research Task

```python
Task(
    description="Research Odoo solutions",
    subagent_type="general-purpose",
    prompt="""Use the Codex agent to research Odoo best practices.
    
    Call mcp__gpt-codex__codex with:
    - prompt: "Research the best practices for implementing Odoo custom modules. 
              Look for existing solutions, GitHub projects, and community patterns.
              Focus on OWL components and ORM optimization."
    - sandbox: "danger-full-access"
    - model: "gpt-5"  # Default, or "gpt-4.1" for 1M+ token context
    """
)
```

#### Implementation Task

```python
Task(
    description="Implement Odoo module",
    subagent_type="general-purpose", 
    prompt="""Use the Codex agent to implement an Odoo module.
    
    Call mcp__gpt-codex__codex with:
    - prompt: "Create a new Odoo module for inventory management.
              Follow Odoo 18 best practices, use OWL components for UI."
    - sandbox: "workspace-write"
    """
)
```

## Model Selection

See: [reference.md#model-selection](../codex/reference.md#model-selection)

## Session Management

See: [reference.md#session-management](../codex/reference.md#session-management)

## Key Capabilities

✅ **Can Do**:

- Execute code and scripts
- Modify files in the project
- Search the web for current information
- Run tests and diagnostics
- Install packages (with appropriate sandbox)
- Make API calls to external services

❌ **Cannot Do**:

- Persist data between separate `codex` calls without session
- Access sensitive credentials (unless in .env files)
- Modify system files outside project (in workspace-write mode)

## Best Practices

1. **Be Specific**: Provide detailed prompts with clear success criteria
2. **Use Sessions**: For multi-step tasks, use session continuations
3. **Choose Right Sandbox**: Start restrictive, escalate if needed
4. **Include Context**: Reference specific files with `@/path/to/file`
5. **Request Output**: Ask Codex to save results to specific files
6. **Optimize Reasoning**: Use `model_reasoning_effort: "high"` for complex tasks
7. **Network Access**: Enable with `sandbox_workspace_write.network_access: true`

## Common Use Cases

### 1. Technology Research

```python
mcp__gpt-codex__codex(
    prompt="Research and compare the top 3 Odoo development patterns. 
            Include pros, cons, and implementation complexity.
            Save analysis to /tmp/odoo-comparison.md",
    sandbox="danger-full-access"
)
```

### 2. Bug Investigation

```python
mcp__gpt-codex__codex(
    prompt="Debug why [Odoo feature] is failing. Check logs, run tests, 
            and provide a fix. Document findings in /tmp/debug-report.md",
    sandbox="workspace-write"
)
```

### 3. Documentation Generation

```python
mcp__gpt-codex__codex(
    prompt="Generate comprehensive documentation for @/addons/ directory.
            Include API docs, usage examples, and architecture overview.",
    sandbox="workspace-write"
)
```

### 4. Performance Optimization

```python
mcp__gpt-codex__codex(
    prompt="Profile and optimize the performance of [Odoo module].
            Run benchmarks before and after. Document improvements.",
    sandbox="workspace-write"
)
```

## Advanced Configuration

See: [advanced.md](../codex/advanced.md)

## Error Handling

See: [reference.md#common-issues](../codex/reference.md#common-issues)

## Integration with Main Workflow

The main assistant should:

1. Identify when a task needs Codex (complex, uncertain, web-required)
2. Use Task() to delegate to this agent
3. This agent handles all Codex MCP interactions
4. Results are incorporated back into main conversation

---

*Note: This agent is designed to handle complex research and implementation tasks that would otherwise consume
significant context in the main conversation.*