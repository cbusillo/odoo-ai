# GPT Model Details & Usage Patterns

## GPT-5 Unified Model (Released August 7, 2025)

### How It Works

- **Unified System**: Smart router automatically switches between fast and deep thinking modes
- **Real-Time Router**: Analyzes and routes to optimal model tier based on complexity
- **Model Tiers** (API): Regular, mini, nano - each with 4 reasoning levels
- **60-80% Fewer Tokens**: More efficient than o3 across all capabilities

### Available Models on ChatGPT.com

| Model                  | Description                                   | When to Use                                 |
|------------------------|-----------------------------------------------|---------------------------------------------|
| **GPT-5**              | Default unified model with auto-routing       | Most development tasks                      |
| **GPT-5 Thinking Pro** | Extended reasoning for Pro/Team users         | Complex problems requiring deep thinking    |
| **GPT-4.5**            | Creative excellence model                     | Marketing copy, storytelling, brand content |
| **GPT-4.1**            | Large context window (1M+ tokens)             | Massive codebases, extensive context        |
| **o3**                 | Analytical reasoning (22% hallucination rate) | Legal/finance analysis (verify outputs)     |

### Performance Benchmarks

**Hallucination Rates**:

- GPT-5: 4.8%
- GPT-4o: 20.6%
- o3: 22%

**Key Improvements**:

- 45% fewer errors than GPT-4o (standard)
- 80% fewer errors than o3 (thinking mode)
- 50-80% more token-efficient than o3

### Context & Performance

- **400K token context** - Standard GPT-5 models
- **1M+ token context** - GPT-4.1 for massive codebases
- **128K max output** - Complete implementations in one response
- **50-80% more efficient** - Fewer tokens than o3 across all tasks
- **Strongest coding model** - Outperforms o3 across all benchmarks

## Advanced Usage Patterns

### Deep Research Mode

```python
mcp__chatgpt_automation__chatgpt_batch_operations(
    operations=[
        {"operation": "new_chat"},
        {"operation": "enable_deep_research"},
        {"operation": "send_and_get_response", "args": {
            "message": "Research Odoo 18 performance patterns",
            "timeout": 300
        }}
    ]
)
```

### Large File Processing

```python
# For 50+ file refactoring
mcp__chatgpt_automation__chatgpt_batch_operations(
    operations=[
        {"operation": "select_model", "args": {"model": "gpt-4.1"}},
        {"operation": "upload_file", "args": {"file_path": "/tmp/codebase.zip"}},
        {"operation": "send_and_get_response", "args": {
            "message": "Refactor all components to Odoo 18 patterns",
            "timeout": 180
        }}
    ]
)
```

### Rate Limit Bypass Strategy

When Claude rate limits hit:

1. Offload large tasks to GPT-5 (0 Claude tokens)
2. Use for 20+ file operations
3. Return summary to Claude for integration

### Common Failure Patterns

1. **Session Timeout**: ChatGPT auto-logs out after 30 min idle
2. **DOM Changes**: Selectors may break with UI updates
3. **Network Issues**: Retry with exponential backoff
4. **Model Switching**: Some models require page refresh

### Best Practices

- Always check `chatgpt_status()` before operations
- Use batch operations for efficiency
- Save conversations for important analyses
- Prefer `send_and_get_response` over separate send/wait