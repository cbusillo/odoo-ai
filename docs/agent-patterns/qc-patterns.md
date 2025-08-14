# 🔍 QC Agent - Quality Control Patterns

This file contains detailed patterns and examples extracted from the QC agent documentation to keep the main agent file
concise.

## Comprehensive Quality Review Workflow

```python
# Complete multi-agent quality assessment
def comprehensive_quality_review(module_name):
    # Phase 1: Code Analysis
    inspector_result = Task(
        description="Deep code analysis",
        prompt=f"@docs/agents/inspector.md\n\nAnalyze {module_name} for all quality issues",
        subagent_type="inspector"
    )
    
    # Phase 2: Performance Check
    flash_result = Task(
        description="Performance analysis",
        prompt=f"@docs/agents/flash.md\n\nCheck {module_name} for performance issues",
        subagent_type="flash"
    )
    
    # Phase 3: Test Coverage
    scout_result = Task(
        description="Test coverage check",
        prompt=f"@docs/agents/scout.md\n\nEvaluate test coverage for {module_name}",
        subagent_type="scout"
    )
    
    # Phase 4: Security Review
    security_check = mcp__odoo-intelligence__pattern_analysis(
        pattern_type="api_decorators"  # Check access controls
    )
    
    return consolidate_results(inspector_result, flash_result, scout_result, security_check)
```

## Pre-Commit Quality Gate Pattern

```python
# Enforce quality before commits
def pre_commit_quality_gate(changed_files):
    issues = []
    
    # Check each changed file
    for file in changed_files:
        # Style and formatting
        if file.endswith('.py'):
            format_check = Bash("ruff check " + file)
            if format_check.returncode != 0:
                issues.append(f"Style issues in {file}")
        
        # Odoo-specific checks
        if "models/" in file:
            field_check = mcp__odoo-intelligence__field_usages(
                model_name=extract_model(file),
                field_name="*"  # Check all fields
            )
            
    if issues:
        # Route fixes to appropriate agents
        fix_task = Task(
            description="Fix quality issues",
            prompt=f"@docs/agents/refactor.md\n\nFix these issues: {issues}",
            subagent_type="refactor"
        )
```

## Cross-Module Consistency Pattern

```python
# Ensure consistency across related modules
def ensure_cross_module_consistency(feature_area):
    # Find all related code
    patterns = mcp__odoo-intelligence__search_code(
        pattern=f"{feature_area}.*",
        file_type="py"
    )
    
    # Check naming conventions
    naming_issues = check_naming_consistency(patterns)
    
    # Check API consistency
    api_issues = check_api_patterns(patterns)
    
    # Coordinate fixes if needed
    if naming_issues or api_issues:
        Task(
            description="Fix consistency issues",
            prompt=f"@docs/agents/refactor.md\n\nStandardize: {naming_issues + api_issues}",
            subagent_type="refactor"
        )
```

## Quality Report Generation

```python
def generate_quality_report(scope="whole_project"):
    return f"""
    🔍 Quality Control Report - {datetime.now()}
    
    Scope: {scope}
    
    ✅ Passed Checks:
    - Code formatting: PASS
    - Import organization: PASS  
    - Type hints present: PASS
    
    ⚠️  Warnings (12):
    - Missing help text: 5 fields
    - Test coverage: 67% (target: 80%)
    - Deprecated patterns: 2 instances
    
    ❌ Critical Issues (3):
    - SQL injection risk: raw_sql() in motor.py:L234
    - N+1 query: product_connect/models/product.py:L456
    - Missing security: motor.part model has no access rules
    
    📊 Metrics:
    - Total files scanned: 89
    - Lines of code: 12,453
    - Cyclomatic complexity: 8.2 (good)
    - Technical debt: 2.3 days
    
    🎯 Recommended Actions:
    1. Fix critical security issues immediately
    2. Add missing field help text
    3. Increase test coverage to 80%+
    """
```

## Error Recovery Integration

```python
from tools.error_recovery import handle_agent_error

def resilient_quality_check(module_name):
    """QC with automatic error recovery and fallbacks."""
    phases = [
        ("inspector", "Code quality analysis"),
        ("flash", "Performance analysis"),
        ("scout", "Test coverage check")
    ]

    results = {}
    for agent, task in phases:
        retry_count = 0
        while retry_count < 3:
            try:
                results[agent] = Task(
                    description=task,
                    prompt=f"@docs/agents/{agent}.md\n\n{task} for {module_name}",
                    subagent_type=agent
                )
                break  # Success, move to next phase
            except Exception as e:
                recovery = handle_agent_error(e, agent, task)

                if recovery["can_retry"] and retry_count < 2:
                    print(f"{agent} failed, retrying in {recovery['retry_delay']:.1f}s...")
                    time.sleep(recovery["retry_delay"])
                    retry_count += 1
                elif recovery["fallback_agent"]:
                    print(f"{agent} failed, using {recovery['fallback_agent']}")
                    results[agent] = Task(
                        description=f"Fallback: {task}",
                        prompt=f"@docs/agents/{recovery['fallback_agent']}.md\n\n{task}",
                        subagent_type=recovery["fallback_agent"]
                    )
                    break
                else:
                    results[agent] = {"error": str(e), "recovery": recovery}
                    break

    return consolidate_results(results)
```

## CI/CD Integration Patterns

```python
# Called from git hooks
def pre_push_quality_check():
    qc_result = Task(
        description="Pre-push quality gate",
        prompt="@docs/agents/qc.md\n\nRun comprehensive quality checks before push",
        subagent_type="qc"
    )
    
    if qc_result.has_blocking_issues:
        raise Exception("Push blocked: Fix quality issues first")

# After feature implementation
def post_feature_quality_review(feature_name):
    Task(
        description="Feature quality review",
        prompt=f"@docs/agents/qc.md\n\nComprehensive review of {feature_name} implementation",
        subagent_type="qc"
    )
```

## Quality Standards Reference

### Code Quality Standards

- **No commented code** - Remove or document properly
- **Consistent naming** - snake_case, descriptive names
- **Type hints** - Python 3.10+ style (no typing imports)
- **No print statements** - Use proper logging
- **DRY principle** - No duplicated code blocks

### Odoo Standards

- **Field help text** - All fields must have help
- **Security rules** - Every model needs access rules
- **Translation marks** - _() for user-facing strings
- **No SQL injection** - Parameterized queries only
- **Proper inheritance** - _inherit vs _name

### Performance Standards

- **No N+1 queries** - Batch operations required
- **Computed stored** - Heavy computations must be stored
- **Proper indexes** - Foreign keys and search fields
- **Lazy evaluation** - Don't compute until needed

### Testing Standards

- **Test coverage** - Minimum 80% for critical paths
- **Test data** - Use base fixtures, not create
- **Test tags** - Proper @tagged decorators
- **No hardcoded IDs** - Use xml_id references

## Specialist Routing Matrix

| Issue Type       | Route To          | Why                      |
|------------------|-------------------|--------------------------|
| Style/formatting | Refactor          | Bulk fixes across files  |
| Performance      | Flash             | Deep optimization needed |
| Missing tests    | Scout             | Test expertise           |
| Frontend issues  | Owl               | JS/CSS knowledge         |
| Security gaps    | Inspector + fixes | Security analysis        |