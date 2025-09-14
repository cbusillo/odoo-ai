# Quality Control Workflow

This file contains detailed patterns and examples extracted from the QC agent documentation to keep the main agent file
concise.

## Comprehensive Quality Review Workflow

Recommended phases

- Code analysis: run scoped inspections (changed→git), fix to zero findings.
- Performance check: scan for known hotpaths, batch operations, and read_group opportunities.
- Test coverage: ensure critical paths have focused tests; add tours only when value justifies.
- Security review: verify ACLs and ir.rule coverage; avoid sudo unless justified.

## Pre-Commit Quality Gate Pattern

Pre-commit gate (policy)

- Style: ruff check and format; commit only when clean.
- Inspections: scope=git for changed files; fix to zero.
- Tests: run unit/js for touched modules; block if failing.

## Cross-Module Consistency Pattern

Cross-module consistency (policy)

- Search related code and consolidate naming/API patterns; apply small, safe batches.

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

Error recovery

- Keep retries explicit and small; prefer fixing root causes over retries.

## CI/CD Integration Patterns

Pre-push guidance

- Ensure inspections (git scope) and targeted tests pass; block push if failing.
- Summarize findings and fixes succinctly in the PR.

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
