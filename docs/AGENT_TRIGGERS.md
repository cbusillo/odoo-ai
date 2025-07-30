# 🎯 Agent Trigger Guide

This document provides detailed scenarios for when Claude should automatically trigger specialized agents. This helps
ensure the right expert handles each type of task.

## 🚨 Error/Debug Scenarios → Debugger Agent

**Trigger Patterns:**

- User shows any Python traceback or error message
- Keywords: "error", "doesn't work", "failing", "crashed", "broken"
- Exception types: AttributeError, ImportError, ValidationError, etc.
- Stack traces or Odoo error dialogs
- "Something's wrong with..."

**Action:**

```python
Task(
    description="Debug error",
    prompt="@docs/agents/debugger.md\n\n[error details]",
    subagent_type="debugger"
)
```

**Examples:**

- "I'm getting this error when trying to create a product..."
- "The module won't update and shows this traceback..."
- "Browser console shows JavaScript errors..."

## 📋 Planning Scenarios → Planner Agent

**Trigger Patterns:**

- "How should I implement..."
- "I want to add feature X"
- "Design a system for..."
- "What's the best approach to..."
- Any complex multi-step feature request
- Architecture questions

**Action:**

```python
Task(
    description="Plan implementation",
    prompt="@docs/agents/planner.md\n\n[feature request]",
    subagent_type="planner"
)
```

**Examples:**

- "I need to build a custom dashboard with multiple graphs"
- "How should I structure the inventory tracking system?"
- "What's the best way to integrate with external APIs?"

## 🔧 Refactoring Scenarios → Refactor Agent

**Trigger Patterns:**

- "Clean up this code"
- "Update all instances of..."
- "Make this consistent across files"
- "Remove redundant..."
- "Rename X to Y everywhere"
- "Standardize the..."

**Action:**

```python
Task(
    description="Refactor code",
    prompt="@docs/agents/refactor.md\n\n[refactoring request]",
    subagent_type="refactor"
)
```

**Examples:**

- "Change all `product_id` references to `product_template_id`"
- "Clean up the duplicate validation methods"
- "Make the error handling consistent across all services"

## 🏹 Research Scenarios → Archer Agent

**Trigger Patterns:**

- "How does Odoo implement..."
- "Find examples of..."
- "What's the pattern for..."
- "Show me how X works in Odoo"
- "Find all models that..."
- "Research the best approach for..."

**Action:**

```python
Task(
    description="Research patterns",
    prompt="@docs/agents/archer.md\n\n[research request]",
    subagent_type="archer"
)
```

**Examples:**

- "How does Odoo handle many2many relationships in views?"
- "Find examples of custom graph views in Odoo 18"
- "What's the standard pattern for computed fields?"

## 🔍 Testing Scenarios → Scout Agent

**Trigger Patterns:**

- "Write tests for..."
- "Test is failing"
- "Add test coverage for..."
- After implementing any feature (proactive)
- "How do I test..."
- "The test suite shows..."

**Action:**

```python
Task(
    description="Write tests",
    prompt="@docs/agents/scout.md\n\n[testing request]",
    subagent_type="scout"
)
```

**Examples:**

- "Write comprehensive tests for the new inventory module"
- "The tour test is failing in the product creation flow"
- "Add unit tests for the validation methods"

## 🔬 Quality Issues → Inspector Agent

**Trigger Patterns:**

- "Check code quality"
- "Find potential issues"
- "Code review needed"
- "Performance problems"
- "Style violations"
- "Clean up warnings"

**Action:**

```python
Task(
    description="Analyze quality",
    prompt="@docs/agents/inspector.md\n\n[quality request]",
    subagent_type="inspector"
)
```

**Examples:**

- "Review the entire product_connect module for issues"
- "Find all performance bottlenecks in the sync code"
- "Check for style guide violations"

## 🚢 Container Issues → Dock Agent

**Trigger Patterns:**

- "Container won't start"
- "Docker issues"
- "Service is down"
- "Module update hanging"
- "Check container logs"
- "Restart services"

**Action:**

```python
Task(
    description="Handle containers",
    prompt="@docs/agents/dock.md\n\n[container issue]",
    subagent_type="dock"
)
```

**Examples:**

- "The web container keeps crashing"
- "Module update is stuck, need to restart script-runner"
- "Check what's wrong with the database connection"

## 🛍️ Shopify Integration → Shopkeeper Agent

**Trigger Patterns:**

- "Shopify sync issues"
- "GraphQL problems"
- "Product export/import"
- "Webhook handling"
- "Shopify API errors"

**Action:**

```python
Task(
    description="Handle Shopify",
    prompt="@docs/agents/shopkeeper.md\n\n[shopify issue]",
    subagent_type="shopkeeper"
)
```

**Examples:**

- "Products aren't syncing to Shopify properly"
- "The webhook is receiving malformed data"
- "Need to implement bulk product export"

## 🦉 Frontend/Owl.js Issues → Owl Agent

**Trigger Patterns:**

- "JavaScript errors"
- "View not rendering"
- "Component issues"
- "Owl.js problems"
- "Frontend debugging"
- "Tour tests failing"

**Action:**

```python
Task(
    description="Fix frontend",
    prompt="@docs/agents/owl.md\n\n[frontend issue]",
    subagent_type="owl"
)
```

**Examples:**

- "The custom graph view isn't displaying data"
- "JavaScript console shows component mounting errors"
- "Need to debug the interactive widget behavior"

## ⚡ Performance Issues → Flash Agent

**Trigger Patterns:**

- "Slow performance"
- "Optimization needed"
- "Database queries taking too long"
- "Memory usage high"
- "Bottlenecks"
- "N+1 query problems"

**Action:**

```python
Task(
    description="Optimize performance",
    prompt="@docs/agents/flash.md\n\n[performance issue]",
    subagent_type="flash"
)
```

**Examples:**

- "The product search is taking 10+ seconds"
- "Inventory calculations are using too much memory"
- "Find all the database query bottlenecks"

## 🎭 Browser Testing → Playwright Agent

**Trigger Patterns:**

- "Tour test failing"
- "UI automation needed"
- "Browser testing"
- "End-to-end test"
- "Interactive debugging"

**Action:**

```python
Task(
    description="Browser testing",
    prompt="@docs/agents/playwright.md\n\n[browser testing request]",
    subagent_type="playwright"
)
```

**Examples:**

- "The checkout flow tour is broken"
- "Need to automate the product creation workflow"
- "Debug why the form submission isn't working"

## 🔥 Migration Issues → Phoenix Agent

**Trigger Patterns:**

- "Legacy code problems"
- "Upgrade issues"
- "Deprecated patterns"
- "Old Odoo version compatibility"
- "Migration needed"

**Action:**

```python
Task(
    description="Handle migration",
    prompt="@docs/agents/phoenix.md\n\n[migration issue]",
    subagent_type="phoenix"
)
```

**Examples:**

- "Update old API decorators to Odoo 18 patterns"
- "Migrate jQuery code to modern JavaScript"
- "Fix deprecated field definitions"

## 🤖 AI Workflow Optimization → Anthropic Engineer

**Trigger Patterns:**

- Questions about Claude Code itself
- "How should I use agents?"
- "Optimize this workflow"
- "Best practices for AI"
- Context management issues

**Action:**

```python
Task(
    description="Optimize workflow",
    prompt="@docs/agents/anthropic-engineer.md\n\n[workflow question]",
    subagent_type="anthropic-engineer"
)
```

**Examples:**

- "What's the most efficient way to handle this complex task?"
- "How can I better structure my prompts?"
- "Should I use multiple agents for this workflow?"

## 💬 Complex Analysis → GPT Agent

**Trigger Patterns:**

- "Review this architecture"
- "Analyze this complex code"
- "What's wrong with this approach?"
- "Compare these implementations"
- Deep technical analysis needed

**Action:**

```python
Task(
    description="Complex analysis",
    prompt="@docs/agents/gpt.md\n\n[analysis request]",
    subagent_type="gpt"
)
```

**Examples:**

- "Review this entire module architecture for flaws"
- "Compare these three different sync strategies"
- "Analyze the performance implications of this design"

## 🎯 Proactive Usage Guidelines

### When Claude Should Be Proactive:

1. **After code changes** → Automatically suggest Scout for testing
2. **On error messages** → Immediately trigger Debugger
3. **Complex requests** → Break down and assign to multiple agents
4. **Code quality concerns** → Proactively run Inspector
5. **Research needed** → Use Archer before implementing

### Agent Combinations:

- **Research + Implementation**: Archer → Planner → Scout
- **Debug + Fix + Test**: Debugger → Refactor → Scout
- **Quality + Performance**: Inspector → Flash → Scout
- **Frontend Issues**: Owl → Playwright → Scout

## 📋 Decision Tree

```
User Request
├── Contains error/traceback? → Debugger Agent
├── Asks "how to implement"? → Planner Agent  
├── Asks "how does Odoo..."? → Archer Agent
├── Mentions testing? → Scout Agent
├── Code quality concern? → Inspector Agent
├── Container issue? → Dock Agent
├── Frontend/JavaScript? → Owl Agent
├── Performance problem? → Flash Agent
├── Shopify related? → Shopkeeper Agent
├── Browser/UI testing? → Playwright Agent
├── Migration/legacy? → Phoenix Agent
├── Complex analysis? → GPT Agent
└── Workflow optimization? → Anthropic Engineer
```

Remember: **Be proactive!** Don't wait for users to explicitly ask for agents. Recognize the patterns and route
appropriately.