# CLAUDE.md

Claude Code guidance for this repository.

## 🎯 Critical Thinking Directive

**ACCURACY OVER AGREEMENT**: The user values being correct more than being agreed with. When you have evidence that contradicts their statement, confidently present the right information. Pattern: "Actually, I think [X] because [evidence]. Here's why [Y] would be better." Be assertive about facts, not opinions.

## Project Overview

Odoo 18 Enterprise project for Outboard Parts Warehouse (OPW). Custom addons for motor parts management with Shopify
integration.  
**Stack**: Python 3.12+, PostgreSQL 17, Owl.js 2.0, Docker, GraphQL  
**Documentation**:
See [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) | [Testing](docs/TESTING.md) | [Style Guide](docs/STYLE_GUIDE.md)

## 🎯 PROACTIVE AGENT USAGE

**CRITICAL**: Claude should automatically use specialized agents. DO NOT use `subagent_type="general-purpose"`!

**Terminology**: When the user refers to "the team" or "our team," they mean the specialized agents (Scout, Owl, Archer, etc.), not human developers.

### When to Use Agents (Automatic Triggers)

| User Says                     | Agent Type | Syntax                       |
|-------------------------------|------------|------------------------------|
| Error/traceback/crash         | debugger   | `subagent_type="debugger"`   |
| "Write tests" (Python/Tour)   | scout      | `subagent_type="scout"`      |
| "Write Hoot tests" (JS/Owl)   | owl        | `subagent_type="owl"`        |
| "Find how Odoo..." / research | archer     | `subagent_type="archer"`     |
| "Clean up" / refactor         | refactor   | `subagent_type="refactor"`   |
| Complex feature planning      | planner    | `subagent_type="planner"`    |
| Frontend/Owl.js issues        | owl        | `subagent_type="owl"`        |
| Docker/container issues       | dock       | `subagent_type="dock"`       |
| Code quality issues           | inspector  | `subagent_type="inspector"`  |
| Quality audit/comprehensive   | qc         | `subagent_type="qc"`         |
| Shopify integration           | shopkeeper | `subagent_type="shopkeeper"` |
| Performance issues            | flash      | `subagent_type="flash"`      |
| "User can't see/access X"     | debugger   | `subagent_type="debugger"` + SHARED_TOOLS |
| "Quick test" / "Check data"   | Any agent  | Include SHARED_TOOLS for `execute_code` |

### Test Writing Routing

| Test Type              | Primary Agent | Supporting Agent | Notes                           |
|------------------------|---------------|------------------|---------------------------------|
| Python Unit Tests      | scout         | -                | Model tests, service tests      |
| Tour Tests (browser)   | scout         | playwright       | UI automation, selectors        |
| Hoot Tests (JS/Owl)    | owl           | scout            | Component tests, service mocks  |
| Integration Tests      | scout         | -                | API tests, workflow tests       |

### Agent Usage Pattern

```python
# Standard invocation - core agent doc only
Task(
    description="Write unit tests",
    prompt="@docs/agents/scout.md\n\nWrite tests for motor model",
    subagent_type="scout"
)

# With subdocs - when agent needs detailed examples
Task(
    description="Write complex tests",
    prompt="@docs/agents/scout.md\n@docs/agents/scout/test-templates.md\n\nWrite integration tests",
    subagent_type="scout"
)

# With SHARED_TOOLS - for specific capabilities
Task(
    description="Debug access rights",
    prompt="@docs/agents/debugger.md\n@docs/agents/SHARED_TOOLS.md\n\nUser can't see records",
    subagent_type="debugger"
)
```

**Loading Additional Context**:

1. **Agent subdocs** (when needed):
   - `scout/test-templates.md` - Detailed test examples
   - `owl/component-patterns.md` - Component examples
   - `refactor/bulk-operations.md` - Bulk refactoring patterns

2. **SHARED_TOOLS.md** (specific tools):
   - Debugging permissions → `permission_checker`
   - Analyzing data → `field_value_analyzer`
   - Quick Python tests → `execute_code`
   - Workflow analysis → `workflow_states`

**See**: [@docs/agents/README.md](docs/agents/README.md) for complete agent guide

## ⚡ Agent-First Architecture (CRITICAL)

**Claude's Role**: Route tasks to specialist agents, coordinate work, maintain conversation context  
**Agents' Role**: Write code, implement features, research, analyze - the actual work

### Who Writes Code?

**✅ AGENTS write all code:**

- **Owl Agent** → Frontend code, CSS, JavaScript, Owl components, Hoot tests
- **Scout Agent** → Python tests, tour tests, test patterns
- **Refactor Agent** → Bulk code changes (coordinates with specialists)
- **Other Agents** → Domain-specific code within their expertise

**✅ CLAUDE orchestrates:**

- Route tasks to appropriate agents
- Coordinate multi-agent workflows
- Answer questions and provide guidance
- Review agent work for completeness

### Agent Routing Hierarchy

1. **AGENT DELEGATION FIRST** - Route to specialist
    - Odoo research → **Archer Agent**
    - Container ops → **Dock Agent**
    - Code quality → **Inspector Agent**
    - Frontend work → **Owl Agent**

2. **DIRECT TOOLS ONLY** - When no agent exists
    - Simple file reads: `Read`, `Grep`, `Glob`
    - Quick checks: `Bash` for basic commands

### Why Agent-First Matters

| Task Type     | Agent Route     | vs Direct Tools     | Benefit                    |
|---------------|-----------------|---------------------|----------------------------|
| Odoo research | Archer Agent    | Direct MCP tools    | Domain expertise + context |
| Code quality  | Inspector Agent | Manual tool usage   | Project-wide analysis      |
| Frontend work | Owl Agent       | Direct file editing | Framework knowledge        |

## 🧠 Smart Context Management (Token Optimization!)

**AUTOMATIC AGENT + MODEL SELECTION**: The system now optimizes for **preserving Claude rate limits** by intelligently offloading to GPT and using efficient models.

### Smart Context Manager

Use `tools/smart_context_manager.py` for intelligent routing:

```python
from tools.smart_context_manager import SmartContextManager

manager = SmartContextManager()
analysis = manager.analyze_task("Implement complete product variant system", file_count=20)

# Result: 
# Agent: gpt + Model: gpt-4.1
# Tokens: 150K-600K tokens  
# Rate Limit Impact: NONE (offloaded to GPT)
# GPT Offload: ✅ YES - Saves Claude tokens!
```

**Automatic Optimizations**:
- **Simple tasks** → Haiku 3.5 (1K-5K tokens) - Minimal rate limit impact
- **Standard development** → Sonnet 4 (15K-50K tokens) - Balanced usage
- **Complex analysis** → Opus 4 (100K-300K tokens) - Consider GPT offload!
- **Large implementations** → GPT-4.1 (ZERO Claude tokens!) - Preserve rate limit

### Usage Examples

```python
# ✅ NEW: Automatic routing based on task analysis
Task(
    description="Smart routing",
    prompt=manager.generate_task_prompt(analysis, "Write unit tests for motor model"),
    subagent_type=analysis.recommended_agent  # Auto-selected: scout
)

# ✅ OLD: Manual routing (still works)
Task(
    description="Manual routing",
    prompt="@docs/agents/scout.md\n\nModel: sonnet-4\n\nWrite unit tests for motor model",
    subagent_type="scout"
)
```

**Smart Features**:
- **Keyword Detection**: "implement complete" → GPT offload (saves 100% Claude tokens)
- **Context Size**: 15+ files → Route to GPT-4.1 (preserves rate limit)
- **Agent Expertise**: Frontend tasks → Owl agent automatically
- **Token Optimization**: Simple tasks → Haiku 3.5 (1K-5K tokens vs 100K+)

### 💡 Claude + GPT Hybrid Development (NEW!)

**Use GPT-4.1 for Large Implementations** - preserves 100% of Claude rate limits:

- **Claude analyzes** using MCP tools → Gathers patterns, context, requirements
- **GPT-4.1 implements** with 1M token context → Generates complete features following your exact patterns
- **Claude validates** with Inspector agent → Ensures quality and compliance

See [@docs/agents/gpt.md](docs/agents/gpt.md) for the complete hybrid development pattern with code examples.

## 🧠 Model Selection Strategy (July 2025)

**CRITICAL**: Optimize for rate limit preservation while maintaining quality by using the right Claude model for each agent.

### Available Models

| Model | Input | Output | Best For |
|-------|-------|--------|----------|
| **Claude Opus 4** | $15/M | $75/M | Complex reasoning, architecture, debugging |
| **Claude Sonnet 4** | $3/M | $15/M | Coding expertise, 72.7% SWE-bench |
| **Claude 3.5 Haiku** | $0.80/M | $4/M | Fast operations, simple tasks |
| **Claude 3.5 Sonnet** | $3/M | $15/M | Previous generation (fallback) |
| **Claude 3.7 Sonnet** | $3/M | $15/M | Hybrid reasoning (specialized cases) |

### Agent Model Assignments

| Agent | Model | Reasoning |
|-------|-------|-----------|
| 🚢 **Dock** | Haiku 3.5 | Simple container ops, speed critical |
| 🏹 **Archer** | Haiku 3.5 | Fast pattern search, volume queries |
| 🔍 **Scout** | Sonnet 4 | Test writing needs coding expertise |
| 🦉 **Owl** | Sonnet 4 | Frontend complexity, framework knowledge |
| 🔬 **Inspector** | Sonnet 4 | Code analysis, pattern detection |
| 🛍️ **Shopkeeper** | Sonnet 4 | GraphQL integration, business logic |
| 🎭 **Playwright** | Sonnet 4 | Browser automation, UI testing |
| 🔧 **Refactor** | Opus 4 | Systematic changes, consistency |
| ⚡ **Flash** | Opus 4 | Performance analysis, bottlenecks |
| 🐛 **Debugger** | Opus 4 | Complex reasoning, root cause analysis |
| 📋 **Planner** | Opus 4 | Architecture design, multi-step reasoning |
| 💬 **GPT** | Opus 4 | Expert consultation, match GPT-4 |
| 🔥 **Phoenix** | Opus 4 | Migration complexity, compatibility |

### Dynamic Model Selection

**Task Complexity Override**: Agents can request higher models for complex tasks:

```python
# Standard coding task (default Sonnet 4)
Task(
    description="Write unit tests",
    prompt="@docs/agents/scout.md\n\nWrite tests for motor model",
    subagent_type="scout"
)

# Complex architectural task (override to Opus 4) 
Task(
    description="Complex test architecture",
    prompt="@docs/agents/scout.md\n\nModel: opus-4\n\nDesign comprehensive test suite for multi-tenant system",
    subagent_type="scout"
)

# Fast simple task (override to Haiku 3.5)
Task(
    description="Quick code review",
    prompt="@docs/agents/inspector.md\n\nModel: haiku-3.5\n\nCheck basic syntax in single file",
    subagent_type="inspector"
)
```

### Rate Limit Optimization Guidelines

**High-Volume Operations (Use Haiku 3.5)**:
- Bulk file searches
- Simple container operations
- Basic pattern matching
- Quick status checks

**Standard Development (Use Sonnet 4)**:
- Code writing and editing
- Test implementation
- Code analysis
- Frontend development

**Complex Analysis (Use Opus 4)**:
- Architecture design
- Complex debugging
- Performance optimization
- Multi-step reasoning
- Expert consultation

### Model Override Syntax

Agents can specify model preferences in their prompts:

```python
# Explicit model request
prompt="@docs/agents/flash.md\n\nModel: opus-4\n\nAnalyze complex performance bottlenecks"

# Fallback specification
prompt="@docs/agents/scout.md\n\nModel: sonnet-4 (fallback: sonnet-3.5)\n\nWrite standard tests"

# Context-aware selection
prompt="@docs/agents/debugger.md\n\nModel: auto\n\nSimple log review" # Uses Haiku 3.5
prompt="@docs/agents/debugger.md\n\nModel: auto\n\nComplex stack trace analysis" # Uses Opus 4
```

### Rate Limit Impact Estimates

**Conservative Usage (Rate Limit Optimized)**:
- Haiku 3.5: Minimal rate limit impact (high-volume simple tasks)
- Sonnet 4: Balanced rate limit usage (standard development)
- Opus 4: Higher rate limit usage (complex reasoning)
- **Combined**: Well within rate limits

**Heavy Development (All Opus)**:
- Opus 4: Maximum rate limit consumption
- **Rate Limit Preservation**: 66% reduction in Claude token usage

*Note: With Pro/Max subscriptions, pricing shown for reference. We optimize for preserving Claude rate limits, not cost savings.*

### Quality Benchmarks

**Agent Performance by Model**:
- **Dock + Haiku**: 2x faster operations, same reliability
- **Scout + Sonnet 4**: 85% test success rate vs 72% with Haiku
- **Flash + Opus**: Finds 95% of performance issues vs 60% with Sonnet
- **Debugger + Opus**: 78% first-try bug fixes vs 45% with Sonnet

## 🚀 Quick Commands

- **Python/Tour Tests**: Route to Scout Agent - See [@docs/agents/scout.md](docs/agents/scout.md)
- **Hoot Tests (JS/Owl)**: Route to Owl Agent - See [@docs/agents/owl.md](docs/agents/owl.md)
- **Format**: `ruff format . && ruff check . --fix` (Claude can run directly)
- **Quality**: Route to Inspector Agent - See [@docs/agents/inspector.md](docs/agents/inspector.md)
- **Containers**: Route to Dock Agent - See [@docs/agents/dock.md](docs/agents/dock.md)
- **Odoo Research**: Route to Archer Agent - See [@docs/agents/archer.md](docs/agents/archer.md)
- **Frontend Work**: Route to Owl Agent - See [@docs/agents/owl.md](docs/agents/owl.md)
- **ChatGPT Analysis**: Route to GPT Agent - See [@docs/agents/gpt.md](docs/agents/gpt.md) (automated!)
- **Performance Guide**: See [docs/TOOL_SELECTION_PERFORMANCE_GUIDE.md](docs/TOOL_SELECTION_PERFORMANCE_GUIDE.md)

## 🏗️ Architecture

**Addons**: `product_connect` (core), `disable_odoo_online`  
**Key Paths**: `./addons` (custom), Database: `opw`  
**DO NOT MODIFY**: `services/shopify/gql/*` (generated), `graphql/schema/*`

**Detailed Architecture**: See [@docs/agents/archer.md](docs/agents/archer.md) for research patterns

## 🔧 Development Workflow

1. **Route tasks to agents** - Don't do the work yourself, delegate to specialists
2. **Check containers** - Use [@docs/agents/dock.md](docs/agents/dock.md)
3. **Run tests** - Use [@docs/agents/scout.md](docs/agents/scout.md)
4. **Code quality** - Use [@docs/agents/inspector.md](docs/agents/inspector.md)

**AGENT FIRST RULE**: Before doing ANY work, ask "Which agent should handle this?" Route to specialists!

## ✅ Success Patterns

### Agent Routing Examples

```python
# ✅ RIGHT: Route code writing to specialist agent
Task(
    description="Fix frontend component",
    prompt="@docs/agents/owl.md\n\nFix this Owl component rendering issue: [code]",
    subagent_type="owl"
)

# ❌ WRONG: Claude writing frontend code directly
Edit("path/to/component.js", old_string="...", new_string="...")
```

### Complex Task Coordination

```python
# ✅ RIGHT: Use multiple agents for complex tasks
# 1. Research with Archer
archer_result = Task(description="Research pattern", prompt="@docs/agents/archer.md\n\nFind Odoo graph view patterns",
                     subagent_type="archer")

# 2. Implement with Owl  
Task(description="Implement component",
     prompt=f"@docs/agents/owl.md\n\nBased on research: {archer_result}\n\nImplement custom graph view",
     subagent_type="owl")

# 3. Test with Scout
Task(description="Write tests", prompt="@docs/agents/scout.md\n\nWrite tests for new graph component",
     subagent_type="scout")
```

### When Claude Acts Directly

**✅ ACCEPTABLE: Simple questions, coordination, file reads**

- Answer user questions about architecture
- Read files to understand context before routing
- Coordinate between multiple agents
- Run basic commands like `ruff format .`

**❌ NEVER: Write code when specialist agent exists**

- Don't write Owl components (use Owl agent)
- Don't write Python models (route to appropriate agent)
- Don't write tests (use Scout agent)

## 📋 Essential Links

- **All Agents**: [@docs/agents/README.md](docs/agents/README.md)
- **Testing Patterns**: [@docs/agents/scout.md](docs/agents/scout.md)
- **Odoo Research**: [@docs/agents/archer.md](docs/agents/archer.md)
- **Code Quality**: [@docs/agents/inspector.md](docs/agents/inspector.md)
- **Docker Operations**: [@docs/agents/dock.md](docs/agents/dock.md)
- **Performance Guide**: [docs/TOOL_SELECTION_PERFORMANCE_GUIDE.md](docs/TOOL_SELECTION_PERFORMANCE_GUIDE.md)
- **Style Standards**: [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md) - Domain-specific style guides