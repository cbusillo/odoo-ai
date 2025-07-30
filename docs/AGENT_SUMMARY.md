# Agent Summary - Quick Reference

One-line descriptions and routing guide for all available agents.

## Core Development Agents

| Agent            | When to Use                                 | Primary Strength                       |
|------------------|---------------------------------------------|----------------------------------------|
| **🏹 Archer**    | "Find how Odoo..." / research Odoo patterns | Odoo source research specialist        |
| **🔍 Scout**     | "Write tests" / failing tests               | Test writing and validation specialist |
| **🔬 Inspector** | Code quality issues / "check code"          | Project-wide quality analysis          |
| **🚢 Dock**      | Docker/container issues / restarts          | Container operations specialist        |
| **🦉 Owl**       | Frontend/Owl.js issues / UI problems        | Frontend development expert            |
| **🔧 Refactor**  | "Clean up" / bulk code changes              | Code improvement and refactoring       |

## Specialized Analysis Agents

| Agent              | When to Use                             | Primary Strength                    |
|--------------------|-----------------------------------------|-------------------------------------|
| **⚡ Flash**        | Performance issues / slow queries       | Performance optimization specialist |
| **🐛 Debugger**    | Error/traceback/crash analysis          | Error investigation and debugging   |
| **📋 Planner**     | Complex feature planning / architecture | Implementation planning specialist  |
| **🛍️ Shopkeeper** | Shopify integration issues              | Shopify sync and GraphQL expert     |
| **🔥 Phoenix**     | Migration/modernization tasks           | Pattern modernization specialist    |

## External Integration Agents

| Agent                     | When to Use                     | Primary Strength                  |
|---------------------------|---------------------------------|-----------------------------------|
| **🎭 Playwright**         | Browser testing / UI automation | Tour test execution and debugging |
| **🤖 GPT**                | Complex analysis / code review  | ChatGPT consultation specialist   |
| **🧙 Odoo Engineer**      | Framework guidance / patterns   | Core Odoo developer perspective   |
| **🤖 Anthropic Engineer** | Claude optimization / workflow  | AI workflow best practices        |

## Quick Agent Selection

### By Task Type

- **Research**: Archer → Find Odoo patterns, inheritance chains
- **Code Quality**: Inspector → Project-wide analysis, performance issues
- **Implementation**: Owl (frontend), Scout (tests), Refactor (cleanup)
- **Operations**: Dock (containers), Debugger (errors), Flash (performance)
- **Planning**: Planner → Break down complex features
- **Integration**: Shopkeeper (Shopify), Playwright (UI testing)

### By Error Type

- **Performance slow**: Flash Agent
- **Tests failing**: Scout Agent
- **Container issues**: Dock Agent
- **JavaScript errors**: Owl Agent → Playwright (if UI testing needed)
- **Python tracebacks**: Debugger Agent
- **Code quality warnings**: Inspector Agent

### By Development Phase

- **Planning**: Planner Agent → Architect the approach
- **Research**: Archer Agent → Find existing patterns
- **Implementation**: Domain agents (Owl, Scout, etc.)
- **Quality Check**: Inspector Agent → Find issues
- **Optimization**: Flash Agent → Performance tuning
- **Testing**: Scout Agent → Write comprehensive tests
- **Deployment**: Dock Agent → Container operations

## Agent Routing Examples

```python
# User: "This code is slow"
Task(
    description="Analyze performance",
    prompt="@docs/agents/flash.md\n\nAnalyze this slow code: [code]",
    subagent_type="flash"
)

# User: "Find how Odoo implements graphs" 
Task(
    description="Research patterns",
    prompt="@docs/agents/archer.md\n\nFind Odoo graph view implementations",
    subagent_type="archer"
)

# User: "Tests are failing"
Task(
    description="Fix tests",
    prompt="@docs/agents/scout.md\n\nFix these failing tests: [errors]",
    subagent_type="scout"
)
```

## Quick Decision Tree

```
User Request
├── Research needed? → Archer Agent
├── Performance issue? → Flash Agent  
├── Test problems? → Scout Agent
├── Container problems? → Dock Agent
├── Frontend issues? → Owl Agent
├── Code quality? → Inspector Agent
├── Complex planning? → Planner Agent
├── Error debugging? → Debugger Agent
└── Simple question? → Claude answers directly
```

## Agent Capabilities Matrix

| Capability                | Core Agents          | Analysis Agents  | Integration Agents      |
|---------------------------|----------------------|------------------|-------------------------|
| **Write code**            | Owl, Scout, Refactor | -                | -                       |
| **Research patterns**     | Archer               | Flash, Inspector | -                       |
| **Run analysis**          | Inspector            | Flash, Debugger  | Playwright              |
| **Manage containers**     | Dock                 | -                | -                       |
| **External consultation** | -                    | -                | GPT, Anthropic Engineer |

## Tips for Agent Selection

1. **Start specific**: Use domain experts (Owl, Scout) before general analysis
2. **Chain agents**: Research (Archer) → Implement (domain agent) → Test (Scout)
3. **Match expertise**: Frontend issues always go to Owl, not Inspector
4. **Performance first**: Use Flash for slow code, not general debugging
5. **Container issues**: Always use Dock, not bash commands

**Remember**: Each agent has specialized tools and knowledge - use the right agent for maximum efficiency!