# Agent Workflows

This guide shows proven workflows for common development tasks using our specialized agents. Each workflow demonstrates
the most efficient tool selection and agent coordination.

## 🎯 Core Principle: Chain Agents for Complex Tasks

Agents work best when focused on their specialty. Chain them together for comprehensive solutions.

## Feature Development Workflow

### 1. Research → 2. Implement → 3. Test → 4. Validate

```python
# Step 1: Research existing patterns
research = Task(
    description="Find similar implementations",
    prompt="""@docs/agents/archer.md
    
    Find how Odoo 18 implements [FEATURE_TYPE] in enterprise modules.
    Focus on: inheritance patterns, view extensions, and best practices.
    """,
    subagent_type="archer"
)

# Step 2: Implement based on findings
implementation = Task(
    description="Implement feature",
    prompt=f"""Based on this research:
    {research}
    
    Implement [FEATURE_DESCRIPTION] following the same patterns.
    """,
    subagent_type="planner"
)

# Step 3: Write comprehensive tests
tests = Task(
    description="Create tests",
    prompt="""@docs/agents/scout.md
    
    Write tests for [FEATURE_NAME]:
    - Unit tests for model methods
    - Integration tests for workflows
    - Tour test for UI interaction
    """,
    subagent_type="scout"
)

# Step 4: Validate quality
validation = Task(
    description="Inspect quality",
    prompt="""@docs/agents/inspector.md
    
    Run comprehensive quality checks on product_connect module.
    Focus on new code added for [FEATURE_NAME].
    """,
    subagent_type="inspector"
)
```

## Bug Investigation Workflow

### Fast Path: Error → Source → Fix → Test

```python
# Step 1: Understand the error
analysis = Task(
    description="Analyze error",
    prompt="""@docs/agents/archer.md
    
    ERROR: [paste error message]
    
    Find where this error originates and similar error handling patterns.
    """,
    subagent_type="archer"
)

# Step 2: Container/log investigation (if needed)
logs = Task(
    description="Check logs",
    prompt="""@docs/agents/dock.md
    
    Get recent logs related to [ERROR_CONTEXT].
    Check all relevant containers.
    """,
    subagent_type="dock"
)

# Step 3: Fix and test
fix = Task(
    description="Fix and verify",
    prompt="""@docs/agents/scout.md
    
    Based on error analysis, create a test that reproduces the bug,
    then implement the fix.
    """,
    subagent_type="scout"
)
```

## Performance Optimization Workflow

### Measure → Analyze → Optimize → Verify

```python
# Step 1: Performance analysis
analysis = Task(
    description="Analyze performance",
    prompt="""@docs/agents/flash.md
    
    Analyze performance issues in [MODEL/FEATURE].
    Focus on: N+1 queries, missing indexes, inefficient computes.
    """,
    subagent_type="flash"
)

# Step 2: Find optimization patterns
patterns = Task(
    description="Find optimizations",
    prompt="""@docs/agents/archer.md
    
    Find how Odoo core optimizes similar operations.
    Look for: batch operations, query optimization, caching.
    """,
    subagent_type="archer"
)

# Step 3: Implement and measure
optimize = Task(
    description="Optimize code",
    prompt=f"""Based on analysis: {analysis}
    And patterns: {patterns}
    
    Implement optimizations and measure improvements.
    """,
    subagent_type="flash"
)
```

## Shopify Integration Workflow

### Import → Process → Sync → Validate

```python
# Step 1: Understand Shopify data
shopify_analysis = Task(
    description="Analyze Shopify data",
    prompt="""@docs/agents/shopkeeper.md
    
    Analyze Shopify [OBJECT_TYPE] structure.
    Map fields to Odoo equivalents.
    """,
    subagent_type="shopkeeper"
)

# Step 2: Implement importer
importer = Task(
    description="Create importer",
    prompt="""@docs/agents/shopkeeper.md
    
    Implement importer for [OBJECT_TYPE].
    Remember: Always use skip_shopify_sync=True context.
    """,
    subagent_type="shopkeeper"
)

# Step 3: Test with mocks
test_sync = Task(
    description="Test integration",
    prompt="""@docs/agents/scout.md
    
    Write tests for Shopify [OBJECT_TYPE] sync.
    Mock all external API calls.
    """,
    subagent_type="scout"
)
```

## Frontend Development Workflow

### Component → Style → Test → Integrate

```python
# Step 1: Research UI patterns
ui_patterns = Task(
    description="Find UI patterns",
    prompt="""@docs/agents/owl.md
    
    Find how Odoo 18 implements [UI_COMPONENT_TYPE].
    Focus on: Owl.js patterns, service usage, asset loading.
    """,
    subagent_type="owl"
)

# Step 2: Implement component
component = Task(
    description="Create component",
    prompt="""@docs/agents/owl.md
    
    Create [COMPONENT_NAME] following Odoo 18 patterns.
    No jQuery, no semicolons, use ES6 modules.
    """,
    subagent_type="owl"
)

# Step 3: Test component
test_ui = Task(
    description="Test UI",
    prompt="""@docs/agents/scout.md
    
    Write Hoot tests for [COMPONENT_NAME].
    Test: rendering, user interaction, state changes.
    """,
    subagent_type="scout"
)
```

## Quick Workflows

### Check Code Quality

```python
Task(
    description="Quick quality check",
    prompt="""@docs/agents/inspector.md
    
    Run pattern analysis on product_connect module.
    Report any critical issues.
    """,
    subagent_type="inspector"
)
```

### Find Implementation Examples

```python
Task(
    description="Find examples",
    prompt="""@docs/agents/archer.md
    
    Find 3 examples of [PATTERN] in Odoo 18 enterprise modules.
    Show the file paths and key code sections.
    """,
    subagent_type="archer"
)
```

### Container Health Check

```python
Task(
    description="Check containers",
    prompt="""@docs/agents/dock.md
    
    Check all container status and recent logs.
    Report any issues or errors.
    """,
    subagent_type="dock"
)
```

## Parallel Agent Execution

For independent tasks, run agents in parallel:

```python
# Launch multiple agents concurrently
results = await Promise.all([
    Task("Find patterns", "@docs/agents/archer.md\n\n..."),
    Task("Check quality", "@docs/agents/inspector.md\n\n..."),
    Task("Analyze performance", "@docs/agents/flash.md\n\n...")
])
```

## Best Practices

### ✅ DO:

- Give agents specific, focused tasks
- Include relevant context from previous agents
- Use the right agent for each specialty
- Chain agents for complex workflows

### ✅ ALWAYS:

- Let Archer research before implementing
- Let Scout handle all test creation
- Let Inspector validate before completion
- Let Dock handle all container operations

### 🎯 REMEMBER:

- Agents have clean context - be explicit
- Include agent docs with @mentions
- Use success patterns from each agent
- Trust agent tool selection

## Specialized Agent Workflows

### Testing Workflows (Scout Agent)

#### Test Development Pipeline

1. **Write comprehensive tests** → Scout agent
2. **Debug browser test issues** → Route to Playwright agent
3. **Frontend test patterns** → Route to Owl agent
4. **Quality check tests** → Route to Inspector agent

#### Test Maintenance

1. **Update failing tests** → Scout agent
2. **Find test patterns** → Route to Archer agent
3. **Container issues** → Route to Dock agent

#### Test Debugging

1. **Analyze test failures** → Scout agent
2. **Debug complex errors** → Route to Debugger agent
3. **Performance test issues** → Route to Flash agent

### Frontend Workflows (Owl Agent)

#### Frontend Development Pipeline

1. **Create/modify components** → Owl agent
2. **Write tests** → Route to Scout agent
3. **Debug browser issues** → Route to Playwright agent
4. **Apply changes** → Route to Dock agent to restart containers

#### Frontend Quality Check

1. **Implement components** → Owl agent
2. **Check code quality** → Route to Inspector agent
3. **Fix bulk issues** → Route to Refactor agent

#### Frontend Troubleshooting

1. **JavaScript errors** → Debug with browser console (Owl)
2. **Asset loading issues** → Check manifests and restart containers (Owl → Dock)
3. **Complex debugging** → Route to Playwright for automated testing
4. **Performance issues** → Route to Flash agent

### Quality & Refactoring Workflows

#### Quality Check Pipeline (Inspector Agent)

1. **Run project-wide analysis** → Inspector agent
2. **Bulk fix issues** → Route to Refactor agent
3. **Validate fixes** → Return to Inspector for verification
4. **Frontend quality** → Route to Owl agent

#### Code Review Process

1. **Comprehensive analysis** → Inspector agent
2. **Performance check** → Route to Flash agent
3. **Architecture review** → Route to GPT agent

#### Coordinated Refactoring (Refactor Agent)

```python
# DELEGATE ANALYSIS: Let specialists find patterns
analysis = Task(
    description="Find refactoring patterns",
    prompt="@docs/agents/archer.md\n\nFind all instances of pattern X that need refactoring",
    subagent_type="archer"
)

# COORDINATE: Plan based on specialist knowledge
# 1. Group by complexity (simple changes first)
# 2. Plan dependency order (base classes before inherited)
# 3. Schedule domain-specific vs bulk operations
# 4. Define validation checkpoints
```

### Container & DevOps Workflows (Dock Agent)

#### After Code Changes

```python
# 1. Check containers running
mcp__docker__list_containers()

# 2. Update module
mcp__odoo_intelligence__odoo_update_module(modules="product_connect")

# 3. Check logs if issues
mcp__docker__fetch_container_logs(container_id="odoo-opw-web-1", tail="all")
```

#### Running Tests

```bash
# Always use script-runner!
./tools/test_runner.py all  # This uses script-runner internally
```

#### Debugging Container Issues

```python
# 1. Check Odoo status
mcp__odoo_intelligence__odoo_status(verbose=True)

# 2. Get recent logs
mcp__odoo_intelligence__odoo_logs(lines=500)

# 3. Restart if needed
mcp__odoo_intelligence__odoo_restart()
```

### Error Investigation Workflows (Debugger Agent)

#### Error Analysis Pipeline

1. **Analyze stack trace** → Debugger agent
2. **Get container logs** → Route to Dock agent
3. **Complex analysis** → Route to GPT agent
4. **Find patterns** → Route to Archer agent

#### Container Issue Investigation

1. **Debug error symptoms** → Debugger agent
2. **Check container status** → Route to Dock agent for logs and status
3. **Restart if needed** → Dock agent handles container operations

#### Code Error Resolution

1. **Parse error message** → Debugger agent
2. **Find similar errors** → Route to Archer for pattern search
3. **Write test case** → Route to Scout agent
4. **Fix and verify** → Implementation agent based on domain

### External Consultation Workflows (GPT Agent)

#### Standard ChatGPT Workflow

1. **Prepare ChatGPT**:
    - Ensure desktop app is open
    - Start new conversation for focused help
    - Select appropriate model from dropdown

2. **Choose Mode**:
    - Standard: Most common tasks
    - Agent mode: Multi-step + research needed
    - Deep Research: Comprehensive investigation

3. **Frame Request**:
    - Be specific about Odoo context
    - Include relevant code snippets
    - Mention performance/security concerns

### Browser Testing Workflows (Playwright Agent)

#### Testing User Workflows

```python
# Login flow
mcp__playwright__browser_navigate(url="http://localhost:8069/web/login")
mcp__playwright__browser_type(
    element="Username field",
    ref="input[name='login']",
    text="admin"
)
mcp__playwright__browser_type(
    element="Password field",
    ref="input[name='password']",
    text="admin"
)
mcp__playwright__browser_click(
    element="Login button",
    ref="button[type='submit']"
)
```

## Workflow Selection Guide

| Task Type        | Primary Workflow         | Alternative Workflow               |
|------------------|--------------------------|------------------------------------|
| New Feature      | Feature Development      | Frontend Development (if UI-heavy) |
| Bug Fix          | Bug Investigation        | Error Analysis Pipeline            |
| Performance      | Performance Optimization | Quality Check Pipeline             |
| Tests Failing    | Test Maintenance         | Test Debugging                     |
| Code Quality     | Quality Check Pipeline   | Coordinated Refactoring            |
| Integration      | Shopify Integration      | External Consultation (complex)    |
| Container Issues | Container & DevOps       | Error Investigation                |
| UI Problems      | Frontend Troubleshooting | Browser Testing                    |