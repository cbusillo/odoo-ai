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
    subagent_type="general-purpose"
)

# Step 2: Implement based on findings
implementation = Task(
    description="Implement feature",
    prompt=f"""Based on this research:
    {research}
    
    Implement [FEATURE_DESCRIPTION] following the same patterns.
    """,
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
)

# Step 4: Validate quality
validation = Task(
    description="Inspect quality",
    prompt="""@docs/agents/inspector.md
    
    Run comprehensive quality checks on product_connect module.
    Focus on new code added for [FEATURE_NAME].
    """,
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
)

# Step 2: Container/log investigation (if needed)
logs = Task(
    description="Check logs",
    prompt="""@docs/agents/dock.md
    
    Get recent logs related to [ERROR_CONTEXT].
    Check all relevant containers.
    """,
    subagent_type="general-purpose"
)

# Step 3: Fix and test
fix = Task(
    description="Fix and verify",
    prompt="""@docs/agents/scout.md
    
    Based on error analysis, create a test that reproduces the bug,
    then implement the fix.
    """,
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
)

# Step 2: Find optimization patterns
patterns = Task(
    description="Find optimizations",
    prompt="""@docs/agents/archer.md
    
    Find how Odoo core optimizes similar operations.
    Look for: batch operations, query optimization, caching.
    """,
    subagent_type="general-purpose"
)

# Step 3: Implement and measure
optimize = Task(
    description="Optimize code",
    prompt=f"""Based on analysis: {analysis}
    And patterns: {patterns}
    
    Implement optimizations and measure improvements.
    """,
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
)

# Step 2: Implement importer
importer = Task(
    description="Create importer",
    prompt="""@docs/agents/shopkeeper.md
    
    Implement importer for [OBJECT_TYPE].
    Remember: Always use skip_shopify_sync=True context.
    """,
    subagent_type="general-purpose"
)

# Step 3: Test with mocks
test_sync = Task(
    description="Test integration",
    prompt="""@docs/agents/scout.md
    
    Write tests for Shopify [OBJECT_TYPE] sync.
    Mock all external API calls.
    """,
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
)

# Step 2: Implement component
component = Task(
    description="Create component",
    prompt="""@docs/agents/owl.md
    
    Create [COMPONENT_NAME] following Odoo 18 patterns.
    No jQuery, no semicolons, use ES6 modules.
    """,
    subagent_type="general-purpose"
)

# Step 3: Test component
test_ui = Task(
    description="Test UI",
    prompt="""@docs/agents/scout.md
    
    Write Hoot tests for [COMPONENT_NAME].
    Test: rendering, user interaction, state changes.
    """,
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
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
    subagent_type="general-purpose"
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