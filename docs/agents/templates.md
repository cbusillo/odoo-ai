# Agent Prompt Templates

Ready-to-use templates for common tasks. Copy, fill in the bracketed values, and execute.

## 🏹 Archer - Research Templates

### Find Implementation Pattern

```python
Task(
    description="Research Odoo pattern",
    prompt="""@docs/agents/archer.md

GOAL: Find how [FEATURE/PATTERN] is implemented in Odoo 18
MODULES: Focus on [enterprise/community] modules
SPECIFIC: Look for [inheritance/views/methods/decorators]
OUTPUT: File paths and code examples
""",
    subagent_type="general-purpose"
)
```

### Analyze Model Structure

```python
Task(
    description="Analyze model",
    prompt="""@docs/agents/archer.md

MODEL: [model.name]
FIND:
1. All fields and their types
2. Computed fields and dependencies  
3. Methods and their decorators
4. Inheritance chain
5. Views using this model
""",
    subagent_type="general-purpose"
)
```

### Find UI Component Examples

```python
Task(
    description="Find UI patterns",
    prompt="""@docs/agents/archer.md

COMPONENT: [widget/view/field] type
FIND: How Odoo 18 implements this in JS
FOCUS: 
- Owl.js component structure
- Service usage
- Asset bundle placement
AVOID: jQuery patterns from older versions
""",
    subagent_type="general-purpose"
)
```

## 🔍 Scout - Testing Templates

### Write Comprehensive Tests

```python
Task(
    description="Create test suite",
    prompt="""@docs/agents/scout.md

FEATURE: [feature name]
MODEL: [model.name]
CREATE:
1. Unit tests for model methods
2. Integration test for workflow
3. Tour test for UI (if applicable)
USE: ProductConnect base classes
MOCK: External services (Shopify, APIs)
""",
    subagent_type="general-purpose"  
)
```

### Test Specific Method

```python
Task(
    description="Test method",
    prompt="""@docs/agents/scout.md

METHOD: [model.name].[method_name]
TEST CASES:
1. Normal operation
2. Edge cases: [empty data/None values/large datasets]
3. Error conditions
4. Permission checks (if applicable)
MOCK: [any external dependencies]
""",
    subagent_type="general-purpose"
)
```

### Fix Failing Test

```python
Task(
    description="Fix test",
    prompt="""@docs/agents/scout.md

FAILING TEST: [TestClass.test_method]
ERROR: [paste error message]
ANALYZE: Why test fails
FIX: Update test or code as needed
ENSURE: Uses proper base classes and SKU validation
""",
    subagent_type="general-purpose"
)
```

## 🔬 Inspector - Quality Templates

### Full Module Inspection

```python
Task(
    description="Inspect module",
    prompt="""@docs/agents/inspector.md

MODULE: [module_name]
RUN:
1. Pattern analysis (all types)
2. Performance analysis on key models
3. Field property analysis
4. Code style compliance
FOCUS ON: New code added recently
REPORT: Critical issues first
""",
    subagent_type="general-purpose"
)
```

### Performance Deep Dive

```python
Task(
    description="Analyze performance",
    prompt="""@docs/agents/inspector.md

MODEL: [model.name]
CHECK FOR:
1. N+1 queries in loops
2. Missing indexes on searched fields
3. Inefficient computed fields
4. Missing field dependencies
5. Unnecessary searches
SUGGEST: Optimizations with examples
""",
    subagent_type="general-purpose"
)
```

## 🚢 Dock - Container Templates

### Container Health Check

```python
Task(
    description="Check containers",
    prompt="""@docs/agents/dock.md

CHECK:
1. All container status
2. Recent logs (last 100 lines each)
3. Any error messages
4. Memory/CPU usage if high
FOCUS: [web-1/script-runner-1/shell-1]
""",
    subagent_type="general-purpose"
)
```

### Module Update & Restart

```python
Task(
    description="Update module",
    prompt="""@docs/agents/dock.md

MODULE: [module_name]
STEPS:
1. Check containers running
2. Update module with proper flags
3. Check logs for errors
4. Restart if needed
USE: script-runner-1 for updates
""",
    subagent_type="general-purpose"
)
```

## 🛍️ Shopkeeper - Integration Templates

### Implement Sync Feature

```python
Task(
    description="Shopify sync",
    prompt="""@docs/agents/shopkeeper.md

SYNC TYPE: [import/export]
OBJECT: [products/orders/customers]
IMPLEMENT:
1. GraphQL query/mutation
2. Field mapping Shopify↔Odoo
3. Error handling
4. Skip sync context usage
REFERENCE: Schema in graphql/schema/
""",
    subagent_type="general-purpose"
)
```

### Debug Sync Issue

```python
Task(
    description="Debug sync",
    prompt="""@docs/agents/shopkeeper.md

ISSUE: [describe sync problem]
OBJECT TYPE: [product/order/customer]
CHECK:
1. Shopify ID fields populated?
2. skip_shopify_sync context used?
3. GraphQL query correct?
4. Field mapping accurate?
5. Error logs in sync_error field?
""",
    subagent_type="general-purpose"
)
```

## 🦉 Owl - Frontend Templates

### Create Owl Component

```python
Task(
    description="Create component",
    prompt="""@docs/agents/owl.md

COMPONENT: [ComponentName]
TYPE: [field widget/view/action]
FEATURES:
1. [list required functionality]
2. [user interactions needed]
USE: Owl.js 2.0 patterns
NO: jQuery, semicolons, old patterns
INCLUDE: Template and registration
""",
    subagent_type="general-purpose"
)
```

### Debug Frontend Error

```python
Task(
    description="Debug UI error",
    prompt="""@docs/agents/owl.md

ERROR: [paste console error]
COMPONENT: [component name if known]
CHECK:
1. Asset bundle placement
2. Import statements
3. Props validation
4. Template syntax
5. Service usage
FIX: Following Odoo 18 patterns
""",
    subagent_type="general-purpose"
)
```

## 🔥 Phoenix - Migration Templates

### Modernize Code Pattern

```python
Task(
    description="Modernize code",
    prompt="""@docs/agents/phoenix.md

FILE/PATTERN: [what to modernize]
CURRENT: Uses [old pattern]
UPGRADE TO: Odoo 18 patterns
SPECIFICALLY:
- Field naming (no _id suffix)
- Type hints (native types)
- No odoo.define in JS
- Remove jQuery usage
""",
    subagent_type="general-purpose"
)
```

## ⚡ Flash - Performance Templates

### Optimize Slow Feature

```python
Task(
    description="Optimize performance",
    prompt="""@docs/agents/flash.md

SLOW OPERATION: [describe what's slow]
CURRENT TIME: [X seconds]
TARGET TIME: [Y seconds]
ANALYZE:
1. Database queries
2. Computed field chains
3. Missing indexes
4. Batch operation opportunities
IMPLEMENT: Most impactful optimizations
""",
    subagent_type="general-purpose"
)
```

## 🔗 Combined Templates

### Complete Feature Implementation

```python
# Research first
research = Task(
    description="Research",
    prompt="""@docs/agents/archer.md
    Find how Odoo implements [SIMILAR_FEATURE]""",
    subagent_type="general-purpose"
)

# Then implement
Task(
    description="Implement",
    prompt=f"""Based on research: {research}
    
    Implement [FEATURE] following same patterns.
    Include: models, views, security, tests""",
    subagent_type="general-purpose"
)
```

### Bug Fix Pipeline

```python
# Investigate
investigation = Task(
    description="Investigate bug",
    prompt="""@docs/agents/archer.md
    
    BUG: [description]
    Find where this occurs and why""",
    subagent_type="general-purpose"
)

# Fix and test
Task(
    description="Fix bug",
    prompt=f"""@docs/agents/scout.md
    
    Based on: {investigation}
    
    1. Write test that reproduces bug
    2. Implement fix
    3. Verify test passes""",
    subagent_type="general-purpose"
)
```

## Usage Tips

1. **Replace [BRACKETS]** with your specific values
2. **Keep context focused** - agents work best with clear, specific tasks
3. **Chain templates** - use output from one as input to another
4. **Add details** - the more specific, the better the results
5. **Trust the agents** - they know which tools to use