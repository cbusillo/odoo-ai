# Tool Selection Guide

## 30-Second Quick Decision

1. **Complex task?** → Route to specialized agent (preserves context)
2. **MCP tool exists?** → Use it (10-100x faster than alternatives)
3. **Simple file operation?** → Read/Write/Edit/Grep/Glob
4. **No other option?** → Bash (document why)

**Key Insight**: Agents work in separate contexts, keeping Claude's main window clean for coordination

## Common Tasks Reference

| Need to...       | Use This                                | Not This                | Why                               |
|------------------|-----------------------------------------|-------------------------|-----------------------------------|
| Write tests      | Scout agent                             | Write directly          | Preserves context, knows patterns |
| Debug error      | Debugger agent                          | Analyze in main context | Complex reasoning isolated        |
| Find patterns    | Archer agent                            | `grep -r`               | Research in separate context      |
| Frontend work    | Owl agent                               | Edit JS directly        | Framework expertise isolated      |
| Code quality     | Inspector agent                         | Manual review           | Full analysis without bloat       |
| Simple search    | `mcp__odoo-intelligence__search_code()` | `bash grep`             | Instant vs 30+ seconds            |
| Container status | `mcp__docker__list_containers()`        | `docker ps`             | Structured data                   |
| Run tests        | `mcp__odoo-intelligence__test_runner()` | `docker exec`           | Proper environment                |

## Why Agents First, Then MCP Tools

### Agents Preserve Context

- Each agent works in a **separate context window**
- Claude's main context stays clean for coordination
- Complex tasks don't bloat the conversation
- Multiple agents can work in parallel

### MCP Tools Are Fast

- **Speed**: 10-100x faster (0.3s vs 30s for searches)
- **Reliability**: Structured output, proper error handling
- **Context**: Understand Odoo relationships, not just text matching
- **Coverage**: Analyze entire codebase, not just visible files

## When Bash Is Actually OK

✅ **Use Bash when:**

- Running custom scripts (use `uv run test-*` commands)
- MCP doesn't support specific flags you need
- Complex piping operations
- One-off system administration

**Document your exception:**

```bash
# Using Bash because MCP doesn't support --dev=all flag
docker exec ${ODOO_PROJECT_NAME}-web-1 /odoo/odoo-bin --dev=all --stop-after-init
```

## Tool Categories

### MCP Tools (`mcp__*`)

- **odoo-intelligence**: Odoo-specific operations (search, analysis, testing)
- **docker**: Container management (status, logs, deployment)
- **pycharm**: IDE operations (single file scope)
- **playwright**: Browser automation
- **gpt-codex**: AI consultation via Codex CLI

### Built-in Tools

- **Read/Write/Edit/MultiEdit**: File operations
- **Grep/Glob**: Pattern matching (when MCP not available)
- **Task**: Launch specialized agents
- **WebFetch/WebSearch**: Documentation lookup

### Bash (Last Resort)

- Custom scripts in the repo
- System operations not covered by MCP
- Always document why MCP wasn't suitable

## Tool Performance Comparison

| Task             | Best (Saves Context)             | Alternative          | Benefit                        |
|------------------|----------------------------------|----------------------|--------------------------------|
| Write code       | Agent (Owl/Scout)                | Direct editing       | Separate context window        |
| Debug error      | Agent (Debugger)                 | Manual analysis      | Complex reasoning isolated     |
| Find patterns    | Agent (Archer)                   | `mcp__search_code()` | Research in separate context   |
| Container ops    | Agent (Dock)                     | `mcp__docker__*`     | Keeps main context clean       |
| Code quality     | Agent (Inspector)                | Manual review        | Full project analysis isolated |
| Simple search    | `mcp__search_code()`             | `bash("grep")`       | <1s vs 30s, structured         |
| Container status | `mcp__docker__list_containers()` | `bash("docker ps")`  | JSON vs text parsing           |

## Performance Impact

| Wrong Choice           | Real Impact  | Example              |
|------------------------|--------------|----------------------|
| `grep` instead of MCP  | 30s wait     | User watches spinner |
| Raw `docker` commands  | Parse errors | Silent test failures |
| Manual file inspection | Missed bugs  | Production issues    |

## Detailed Performance Analysis

### MCP vs Generic Tool Performance

**Key Insight**: MCP tools are purpose-built and optimized. They consistently outperform generic alternatives by
10-100x.

| Operation            | MCP Tool                                     | Generic Tool  | Speed Difference   | Why It Matters     |
|----------------------|----------------------------------------------|---------------|--------------------|--------------------|
| Search code patterns | `mcp__odoo-intelligence__search_code`        | `bash grep`   | **100x faster**    | <1s vs 30s+        |
| Container status     | `mcp__docker__list_containers`               | `docker ps`   | **10x faster**     | Structured data    |
| Code quality check   | `mcp__odoo-intelligence__analysis_query`     | Manual review | **1000x coverage** | Entire project     |
| Module update        | `mcp__odoo-intelligence__odoo_update_module` | `docker exec` | **5x safer**       | Proper environment |
| File search          | `Glob`                                       | `bash find`   | **50x faster**     | Optimized patterns |

### Real-World Performance Examples

#### Code Search Operations

**❌ SLOW: Bash grep through Docker**

```python
# Takes 30+ seconds, requires parsing
bash("docker exec ${ODOO_PROJECT_NAME}-web-1 grep -r 'class.*Controller' /odoo/addons/")
```

**Problems**:

- Searches entire filesystem
- No caching or indexing
- Raw text output needs parsing
- Can timeout on large codebases

**✅ FAST: MCP Odoo Intelligence**

```python
# Returns in <1 second with structured data
mcp__odoo-intelligence__search_code(
    pattern="class.*Controller",
    file_type="py"
)
```

**Benefits**:

- Pre-indexed search
- Returns structured JSON
- Filters by file type
- Includes context and line numbers

#### Container Operations

**❌ INEFFICIENT: Raw Docker Commands**

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

**✅ OPTIMAL: MCP Docker Tools**

```python
# Single call, complete structured data
containers = mcp__docker__list_containers()
# Returns: [{"name": "${ODOO_PROJECT_NAME}-web-1", "status": "running", "ports": {...}, ...}]
```

**Benefits**:

- Single API call
- Complete container info
- Proper error handling
- Type-safe data structures

#### Code Quality Analysis

**❌ LIMITED: File-by-File Inspection**

```python
# Only analyzes currently open file
mcp__inspection-pycharm__inspection_trigger()
# Wait...
mcp__inspection-pycharm__inspection_get_problems()
```

**Problems**:

- Single file scope
- Misses cross-file issues
- No pattern detection
- Manual aggregation needed

**✅ COMPREHENSIVE: Project-Wide Analysis**

```python
# Analyzes entire codebase systematically
mcp__odoo-intelligence__analysis_query(analysis_type="patterns", pattern_type="all")
mcp__odoo-intelligence__analysis_query(analysis_type="performance", model_name="product.template")
```

**Benefits**:

- Entire project coverage
- Finds systemic issues
- Pattern recognition
- Performance bottlenecks

### Performance Patterns by Task Type

#### Pattern 1: Bulk Search Operations

**Task**: Find all models using specific decorator

```python
# ✅ RIGHT: Single optimized search
models = mcp__odoo-intelligence__search_decorators(decorator="depends")
# Time: <2 seconds for entire codebase

# ❌ WRONG: Multiple file reads
files = Glob("**/*.py")
for file in files[:100]:  # Can only handle subset
    content = Read(file)
    # Manual parsing...
# Time: 2+ minutes for subset only
```

#### Pattern 2: Container Management

**Task**: Restart specific services after code change

```python
# ✅ RIGHT: Targeted restart
mcp__odoo-intelligence__odoo_restart(services="web-1,shell-1")
# Time: 5 seconds

# ❌ WRONG: Full stack restart
bash("docker-compose down && docker-compose up -d")
# Time: 30+ seconds, disrupts everything
```

#### Pattern 3: Module Development Cycle

**Task**: Update module and check for issues

```python
# ✅ RIGHT: Integrated workflow
# 1. Update with proper flags
mcp__odoo-intelligence__odoo_update_module(
    modules="product_connect",
    force_install=True
)
# 2. Check logs efficiently  
mcp__odoo-intelligence__odoo_logs(lines=100)
# Total time: 10 seconds

# ❌ WRONG: Manual process
# 1. Wrong container (interferes with web)
bash("docker exec ${ODOO_PROJECT_NAME}-web-1 /odoo/odoo-bin -u product_connect")
# 2. Full log dump
bash("docker logs ${ODOO_PROJECT_NAME}-web-1")
# Total time: 45+ seconds, potential issues
```

### Performance Anti-Patterns to Avoid

#### Anti-Pattern 1: Using Bash for File Search

```python
# ❌ DON'T: Slow and error-prone
bash("find . -name '*.xml' -exec grep -l 'ir.ui.view' {} \\;")

# ✅ DO: Fast and structured
mcp__odoo-intelligence__search_code(
    pattern='model="ir.ui.view"',
    file_type="xml"
)
```

#### Anti-Pattern 2: Multiple Docker Exec Calls

```python
# ❌ DON'T: Multiple subprocess overhead
bash("docker exec ${ODOO_PROJECT_NAME}-web-1 ls /odoo/addons")
bash("docker exec ${ODOO_PROJECT_NAME}-web-1 cat /odoo/addons/base/__manifest__.py")

# ✅ DO: Use appropriate tools
mcp__odoo-intelligence__module_structure(module_name="base")
```

#### Anti-Pattern 3: Parsing Unstructured Output

```python
# ❌ DON'T: Fragile text parsing
output = bash("docker ps")
# Complex regex to parse table format...

# ✅ DO: Get structured data directly
containers = mcp__docker__list_containers()
running = [c for c in containers if c["status"] == "running"]
```

### Tool Selection Decision Tree

```
Need to search code?
├─ YES → Use mcp__odoo-intelligence__search_* tools
│   ├─ Search by pattern → search_code()
│   ├─ Find models → model_query(operation="search")
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

### Performance Rules of Thumb

1. **MCP tools first** - They're optimized for the task
2. **Built-in tools second** - When MCP doesn't cover it
3. **Bash last resort** - Only for uncovered operations
4. **Batch when possible** - Reduce call overhead
5. **Cache when repeating** - Avoid redundant operations

### Quick Performance Reference

**Always Use These First:**

- **Code Search**: `mcp__odoo-intelligence__search_*`
- **Container Ops**: `mcp__docker__*`
- **File Patterns**: `Glob()` not `find`
- **File Reading**: `Read()` not `cat`
- **Module Updates**: `mcp__odoo-intelligence__odoo_update_module()`

**Never Do These:**

- ❌ `bash("grep -r ...")` → Use MCP search tools
- ❌ `bash("docker ps")` → Use `mcp__docker__list_containers()`
- ❌ `bash("find . -name")` → Use `Glob()`
- ❌ Run tests in web-1 → Use script-runner-1
- ❌ Parse text output → Use tools that return JSON

## Need Help?

- **Not sure which tool?** → Check the quick reference above
- **Complex task?** → Route to appropriate agent
- **Tool not working?** → Document the issue, use fallback
- **Want benchmarks?** → See [Performance Reference Guide](PERFORMANCE_REFERENCE.md)

## Conclusion

The performance difference between optimal and suboptimal tool choice is dramatic:

- **Search operations**: 100x faster with MCP tools
- **Container operations**: 10x faster with proper tools
- **Quality analysis**: 1000x better coverage
- **Development cycle**: 3-5x faster overall

By following these patterns, you can significantly improve development speed and reduce waiting time. The key is knowing
which tool is purpose-built for your task.

Remember: Using the right tool makes development 3-5x faster. The few seconds to check this guide save minutes of
waiting.
