# ChatGPT Analysis Patterns

## Model Selection by Task Type (July 2025)

### Code Review Analysis

**Standard Reviews** (Most Common):
- **Model**: o4-mini-high (default choice)
- **Mode**: Standard
- **Pattern**: "Review this Odoo [method/class/module] for [performance/security/maintainability] issues"
- **Why**: Best balance of speed (0.8-1.5s) and coding accuracy

**Complex Business Logic Review**:
- **Model**: o3
- **Mode**: Standard
- **Pattern**: "Analyze this complex [business workflow/algorithm] for logical correctness and edge cases"
- **Why**: Deep reasoning needed (1-2s wait justified)

**Critical Production Code**:
- **Model**: o3-pro (use sparingly - can take 10+ minutes!)
- **Mode**: Standard  
- **Pattern**: "Critically analyze this [security/compliance/financial] code for any potential issues"
- **When**: Final sign-off on GDPR, financial calculations, security modules

### Architecture Consultation

**System Design**:
- **Model**: o3
- **Mode**: Web search enabled
- **Pattern**: "Research current best practices for [Odoo architecture pattern] and recommend approach for [specific requirements]"
- **Gets**: Latest techniques + reasoned recommendations

**Massive Refactoring Planning**:
- **Model**: GPT-4.1 or GPT-4.1-mini
- **Mode**: Standard
- **Pattern**: "Analyze these 100+ files and create refactoring plan for [modernization goal]"
- **Why**: 1M token context window handles entire codebase

### Performance Analysis

**Standard Performance Issues**:
- **Model**: o4-mini-high
- **Mode**: Standard
- **Pattern**: "Analyze this [workflow/query/method] for performance bottlenecks"
- **Why**: Fast enough for iterative optimization

**Complex Multi-System Performance**:
- **Model**: o3
- **Mode**: Web search enabled
- **Pattern**: "Research and analyze performance issues across [multiple systems] with current optimization techniques"
- **When**: Cross-system bottlenecks, distributed performance

### Daily Development Tasks

**CRUD/API Generation**:
- **Model**: o4-mini (fastest)
- **Mode**: Standard
- **Pattern**: "Generate [model/controller/test] for [feature] following Odoo patterns"
- **Why**: 0.5-1s response for routine scaffolding

**Frontend JS/Owl.js**:
- **Model**: o4-mini-high
- **Mode**: Standard
- **Pattern**: "Create Owl component for [UI feature] with [specific behavior]"
- **Why**: Good at DOM logic and event handling

**Unit Test Writing**:
- **Model**: o4-mini
- **Mode**: Standard
- **Pattern**: "Write comprehensive unit tests for [method/class]"
- **Why**: Fast generation of test patterns

### Learning & Documentation

**Technical Explanations**:
- **Model**: GPT-4o (multimodal)
- **Mode**: Standard
- **Pattern**: "Explain [Odoo concept/pattern] with visual diagrams and examples"
- **Why**: Can process screenshots, create visual explanations

**API Documentation**:
- **Model**: o4-mini-high
- **Mode**: Standard
- **Pattern**: "Generate API documentation for [module] with examples"
- **Why**: Good balance for technical writing

### Quick Problem Solving

**Syntax/Logic Fixes**:
- **Model**: o4-mini
- **Mode**: Standard
- **Pattern**: "Fix this [Python/JS] error: [code snippet]"
- **Why**: Sub-second response for simple fixes

**Debugging Complex Issues**:
- **Model**: o3
- **Mode**: Standard
- **Pattern**: "Debug this issue: [stack trace + code context]"
- **Why**: Reasoning through complex error chains

## Agent Collaboration Patterns

### Debugger → ChatGPT Flow
```python
# After Debugger finds complex error
Task(
    description="Deep error analysis",
    prompt="""@docs/agents/gpt.md

Model: o3
Mode: Agent (research similar issues)

Analyze this stack trace and research solutions:
[error details from Debugger]
    
Focus on: root cause, similar issues, proven fixes""",
    subagent_type="gpt"
)
```

### Archer → ChatGPT Flow
```python
# After Archer finds patterns
Task(
    description="Pattern explanation",
    prompt="""@docs/agents/gpt.md

Model: GPT-4o
Mode: Deep Research

Explain this Odoo pattern found in codebase:
[pattern details from Archer]

Include: purpose, alternatives, best practices""",
    subagent_type="gpt"
)
```

### Flash → ChatGPT Flow
```python
# After Flash identifies performance issues
Task(
    description="Performance consultation",
    prompt="""@docs/agents/gpt.md

Model: o3
Mode: Agent (research latest techniques)

These performance issues were found:
[issues from Flash]

Research: latest optimization patterns, similar case studies""",
    subagent_type="gpt"
)
```

## Conversation Management

### New vs Continuing Conversations

**Start New When**:
- ✅ Completely different topic/module
- ✅ Need fresh analysis perspective
- ✅ Previous conversation became too long

**Continue Existing When**:
- ✅ Iterative refinement of same issue
- ✅ Building on previous recommendations
- ✅ Related follow-up questions

### Context Building Strategy

**Progressive Detail**:
1. Start with high-level question
2. Dive deeper based on initial response
3. Ask for specific code examples
4. Request implementation guidance

**Example Flow**:
```
Initial: "What's the best approach for Odoo inventory optimization?"
Follow-up: "How would that work with our multi-warehouse setup?"
Detailed: "Show me the specific compute method structure for this"
Implementation: "What tests should I write for this approach?"
```

## Usage Optimization

### Managing Limits

**Agent Mode** (400 queries/month):
- Use for research-heavy tasks only
- Standard mode sufficient for most analysis
- Monitor usage in ChatGPT settings

**Deep Research** (time-intensive):
- Reserve for comprehensive learning
- Best for broad topic exploration
- Allow 10+ minutes per query

### Model Selection Strategy

**Speed vs Quality Trade-offs**:

| Model | Speed | Quality | Use Case |
|-------|-------|---------|----------|
| o4-mini | 0.5-1s | Good for basics | High-volume tasks, simple scripts |
| o4-mini-high | 0.8-1.5s | Excellent coding | **DEFAULT** - best balance |
| o3 | 1-2s | Deep reasoning | Complex logic, architecture |
| o3-pro | 2-4s (queues 10+min) | Highest accuracy | Critical audits only |
| GPT-4.1-mini | ~5s | Good with context | Large file analysis |
| GPT-4.1 | 15s-1min | Best for huge context | Massive refactors |

**Model Selection Guide**:
1. Start with o4-mini-high (covers 80% of needs)
2. Drop to o4-mini for maximum speed on simple tasks
3. Upgrade to o3 for complex reasoning (worth the wait)
4. Reserve o3-pro for mission-critical reviews (10+ min wait)
5. Use GPT-4.1 variants when context >200K tokens

**Mode Selection**:
- Standard mode: Most tasks (no quota limit)
- Web search: Current info, latest practices
- Agent mode: Deep research (400/month limit)
- Deep Research: Comprehensive learning (10+ min)

## Error Patterns & Solutions

### Common ChatGPT Issues

**"I need more context"**:
- Provide specific code snippets
- Include error messages/stack traces
- Mention Odoo version and modules involved

**Generic responses**:
- Ask for specific implementation details
- Request code examples
- Follow up with "How would this work in our specific case?"

**Outdated suggestions**:
- Mention "for Odoo 18" explicitly
- Ask for "current best practices as of 2025"
- Enable Search mode for latest info

### Debugging Collaboration Issues

**ChatGPT gives different advice than Claude**:
- Provide both perspectives to ChatGPT
- Ask for reconciliation/comparison
- Focus on trade-offs of each approach

**Analysis seems shallow**:
- Switch to o3 or o3-pro model
- Enable Agent mode for research
- Ask specific follow-up questions