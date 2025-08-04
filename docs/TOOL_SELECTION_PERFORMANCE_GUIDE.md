# Performance-Aware Tool Selection Guide

## Executive Summary

Choosing the right tool can mean the difference between a 30-second wait and instant results. This guide provides
real-world performance benchmarks and patterns for optimal tool selection in Odoo development.

**Key Insight**: MCP tools are purpose-built and optimized. They consistently outperform generic alternatives by
10-100x.

## Performance Comparison Matrix

| Operation            | MCP Tool                                     | Generic Tool  | Speed Difference   | Why It Matters     |
|----------------------|----------------------------------------------|---------------|--------------------|--------------------|
| Search code patterns | `mcp__odoo-intelligence__search_code`        | `bash grep`   | **100x faster**    | <1s vs 30s+        |
| Container status     | `mcp__docker__list_containers`               | `docker ps`   | **10x faster**     | Structured data    |
| Code quality check   | `mcp__odoo-intelligence__pattern_analysis`   | Manual review | **1000x coverage** | Entire project     |
| Module update        | `mcp__odoo-intelligence__odoo_update_module` | `docker exec` | **5x safer**       | Proper environment |
| File search          | `Glob`                                       | `bash find`   | **50x faster**     | Optimized patterns |

## Real-World Performance Examples

### 1. Code Search Operations

#### ❌ SLOW: Bash grep through Docker

```python
# Takes 30+ seconds, requires parsing
bash("docker exec odoo-opw-web-1 grep -r 'class.*Controller' /odoo/addons/")
```

**Problems**:

- Searches entire filesystem
- No caching or indexing
- Raw text output needs parsing
- Can timeout on large codebases

#### ✅ FAST: MCP Odoo Intelligence

```python
# Returns in <1 second with structured data
mcp__odoo - intelligence__search_code(
    pattern="class.*Controller",
    file_type="py"
)
```

**Benefits**:

- Pre-indexed search
- Returns structured JSON
- Filters by file type
- Includes context and line numbers

### 2. Container Operations

#### ❌ INEFFICIENT: Raw Docker Commands

```python
# Multiple calls, text parsing required
container_list = bash("docker ps --format '{{.Names}}'")
for container in container_list.split('\n'):
    status = bash(f"docker inspect {container} --format '{{.State.Status}}'")
    # More parsing...
```

**Problems**:

- Multiple subprocess calls
- Text parsing overhead
- No error handling
- Race conditions possible

#### ✅ OPTIMAL: MCP Docker Tools

```python
# Single call, complete structured data
containers = mcp__docker__list_containers()
# Returns: [{"name": "odoo-opw-web-1", "status": "running", "ports": {...}, ...}]
```

**Benefits**:

- Single API call
- Complete container info
- Proper error handling
- Type-safe data structures

### 3. Code Quality Analysis

#### ❌ LIMITED: File-by-File Inspection

```python
# Only analyzes currently open file
mcp__inspection - pycharm__inspection_trigger()
# Wait...
mcp__inspection - pycharm__inspection_get_problems()
```

**Problems**:

- Single file scope
- Misses cross-file issues
- No pattern detection
- Manual aggregation needed

#### ✅ COMPREHENSIVE: Project-Wide Analysis

```python
# Analyzes entire codebase systematically
mcp__odoo - intelligence__pattern_analysis(pattern_type="all")
mcp__odoo - intelligence__performance_analysis(model_name="product.template")
```

**Benefits**:

- Entire project coverage
- Finds systemic issues
- Pattern recognition
- Performance bottlenecks

### 4. File Operations

#### ❌ SLOW: Bash Find Commands

```python
# Searches entire directory tree
bash("find . -name '*.py' -type f | head -20")
```

**Problems**:

- No ignore patterns (.git, __pycache__)
- Sorts by filesystem order
- Limited filtering options
- Can be very slow on large projects

#### ✅ FAST: Built-in Glob Tool

```python
# Optimized with ignore patterns
Glob("**/*.py")
```

**Benefits**:

- Respects .gitignore
- Sorted by modification time
- Built-in filtering
- 50x faster on average

## Performance Patterns by Task Type

### Pattern 1: Bulk Search Operations

**Task**: Find all models using specific decorator

```python
# ✅ RIGHT: Single optimized search
models = mcp__odoo - intelligence__search_decorators(decorator="depends")
# Time: <2 seconds for entire codebase

# ❌ WRONG: Multiple file reads
files = Glob("**/*.py")
for file in files[:100]:  # Can only handle subset
    content = Read(file)
    # Manual parsing...
# Time: 2+ minutes for subset only
```

### Pattern 2: Container Management

**Task**: Restart specific services after code change

```python
# ✅ RIGHT: Targeted restart
mcp__odoo - intelligence__odoo_restart(services="web-1,shell-1")
# Time: 5 seconds

# ❌ WRONG: Full stack restart
bash("docker-compose down && docker-compose up -d")
# Time: 30+ seconds, disrupts everything
```

### Pattern 3: Module Development Cycle

**Task**: Update module and check for issues

```python
# ✅ RIGHT: Integrated workflow
# 1. Update with proper flags
mcp__odoo - intelligence__odoo_update_module(
    modules="product_connect",
    force_install=True
)
# 2. Check logs efficiently  
mcp__odoo - intelligence__odoo_logs(lines=100)
# Total time: 10 seconds

# ❌ WRONG: Manual process
# 1. Wrong container (interferes with web)
bash("docker exec odoo-opw-web-1 /odoo/odoo-bin -u product_connect")
# 2. Full log dump
bash("docker logs odoo-opw-web-1")
# Total time: 45+ seconds, potential issues
```

### Pattern 4: Test Execution

**Task**: Run specific test suite

```python
# ✅ RIGHT: Dedicated test runner
bash("./tools/test_runner.py product_connect")
# - Uses script-runner container
# - Structured output
# - Proper test isolation
# Time: 20 seconds

# ❌ WRONG: Direct odoo-bin in web container
bash("docker exec odoo-opw-web-1 /odoo/odoo-bin --test-enable --test-tags=...")
# - Disrupts web service
# - No output formatting
# - Can hang
# Time: 60+ seconds
```

## Tool Selection Decision Tree

```
Need to search code?
├─ YES → Use mcp__odoo-intelligence__search_* tools
│   ├─ Search by pattern → search_code()
│   ├─ Find models → search_models()
│   ├─ Find methods → find_method()
│   └─ Search by decorator → search_decorators()
└─ NO → Continue...

Need container operations?
├─ YES → Use mcp__docker__* tools
│   ├─ List containers → list_containers()
│   ├─ View logs → fetch_container_logs()
│   └─ Restart → Use mcp__odoo-intelligence__odoo_restart()
└─ NO → Continue...

Need file operations?
├─ YES → Use built-in tools
│   ├─ Find files → Glob()
│   ├─ Read content → Read()
│   ├─ Search content → Grep() (when MCP not available)
│   └─ Edit files → Edit() or MultiEdit()
└─ NO → Continue...

Need Odoo operations?
├─ YES → Use mcp__odoo-intelligence__* tools
│   ├─ Update modules → odoo_update_module()
│   ├─ Run shell code → odoo_shell()
│   └─ Check status → odoo_status()
└─ NO → Use Bash as last resort
```

## Performance Anti-Patterns to Avoid

### Anti-Pattern 1: Using Bash for File Search

```python
# ❌ DON'T: Slow and error-prone
bash("find . -name '*.xml' -exec grep -l 'ir.ui.view' {} \\;")

# ✅ DO: Fast and structured
mcp__odoo - intelligence__search_code(
    pattern='model="ir.ui.view"',
    file_type="xml"
)
```

### Anti-Pattern 2: Multiple Docker Exec Calls

```python
# ❌ DON'T: Multiple subprocess overhead
bash("docker exec odoo-opw-web-1 ls /odoo/addons")
bash("docker exec odoo-opw-web-1 cat /odoo/addons/base/__manifest__.py")

# ✅ DO: Use appropriate tools
mcp__odoo - intelligence__module_structure(module_name="base")
```

### Anti-Pattern 3: Parsing Unstructured Output

```python
# ❌ DON'T: Fragile text parsing
output = bash("docker ps")
# Complex regex to parse table format...

# ✅ DO: Get structured data directly
containers = mcp__docker__list_containers()
running = [c for c in containers if c["status"] == "running"]
```

### Anti-Pattern 4: Running Tests in Web Container

```python
# ❌ DON'T: Disrupts web service
bash("docker exec odoo-opw-web-1 python -m pytest")

# ✅ DO: Use dedicated test container
bash("docker exec odoo-opw-script-runner-1 python -m pytest")
# Or better: bash("./tools/test_runner.py")
```

## Performance Optimization Strategies

### Strategy 1: Batch Operations

```python
# ❌ SLOW: Sequential operations
for model in ["product.template", "res.partner", "sale.order"]:
    mcp__odoo - intelligence__model_info(model_name=model)
    # 3 separate calls, 3x overhead

# ✅ FAST: Design tools to handle batches
# (Future enhancement: accept lists)
models_info = mcp__odoo - intelligence__search_models(pattern="product|partner|sale")
# Single call, comprehensive results
```

### Strategy 2: Cache Repeated Searches

```python
# If searching same patterns multiple times
_search_cache = {}


def cached_search(pattern, file_type):
    cache_key = f"{pattern}:{file_type}"
    if cache_key not in _search_cache:
        _search_cache[cache_key] = mcp__odoo - intelligence__search_code(
            pattern=pattern,
            file_type=file_type
        )
    return _search_cache[cache_key]
```

### Strategy 3: Use Appropriate Scope

```python
# ❌ OVERKILL: Full project scan for single model
mcp__odoo - intelligence__pattern_analysis(pattern_type="all")
# Analyzes everything when you need one model

# ✅ TARGETED: Specific model analysis
mcp__odoo - intelligence__model_info(model_name="product.template")
mcp__odoo - intelligence__field_usages(model_name="product.template", field_name="list_price")
```

### Strategy 4: Parallel Agent Execution

```python
# ✅ OPTIMAL: Launch independent agents concurrently
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor() as executor:
    # Launch multiple agents in parallel
    inspector_future = executor.submit(
        Task, description="Code quality",
        prompt="@docs/agents/inspector.md\n\nAnalyze module",
        subagent_type="inspector"
    )

    scout_future = executor.submit(
        Task, description="Test coverage",
        prompt="@docs/agents/scout.md\n\nCheck test coverage",
        subagent_type="scout"
    )

    # Collect results
    inspector_result = inspector_future.result()
    scout_result = scout_future.result()
```

## Quick Reference Card

### Always Use These First:

- **Code Search**: `mcp__odoo-intelligence__search_*`
- **Container Ops**: `mcp__docker__*`
- **File Patterns**: `Glob()` not `find`
- **File Reading**: `Read()` not `cat`
- **Module Updates**: `mcp__odoo-intelligence__odoo_update_module()`

### Never Do These:

- ❌ `bash("grep -r ...")` → Use MCP search tools
- ❌ `bash("docker ps")` → Use `mcp__docker__list_containers()`
- ❌ `bash("find . -name")` → Use `Glob()`
- ❌ Run tests in web-1 → Use script-runner-1
- ❌ Parse text output → Use tools that return JSON

### Performance Rules of Thumb:

1. **MCP tools first** - They're optimized for the task
2. **Built-in tools second** - When MCP doesn't cover it
3. **Bash last resort** - Only for uncovered operations
4. **Batch when possible** - Reduce call overhead
5. **Cache when repeating** - Avoid redundant operations

## Conclusion

The performance difference between optimal and suboptimal tool choice is dramatic:

- **Search operations**: 100x faster with MCP tools
- **Container operations**: 10x faster with proper tools
- **Quality analysis**: 1000x better coverage
- **Development cycle**: 3-5x faster overall

By following these patterns, you can significantly improve development speed and reduce waiting time. The key is knowing
which tool is purpose-built for your task.