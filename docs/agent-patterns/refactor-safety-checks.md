# Refactor Safety Guide

Critical safety practices for refactoring operations.

## Pre-Refactoring Checklist

### 1. Backup Current State

```bash
# Commit current state
git add -A
git commit -m "Pre-refactoring checkpoint"

# Create safety branch
git checkout -b refactoring-safety
```

### 2. Analyze Impact

```python
# Check dependencies
dependencies = mcp__odoo-intelligence__field_query(
    operation="dependencies",
    model_name="product.template",
    field_name="name"
)

# Find all usages
usages = mcp__odoo-intelligence__field_query(
    operation="usages",
    model_name="product.template",
    field_name="name"
)

# Check inheritance chain
chain = mcp__odoo-intelligence__model_query(
    operation="inheritance",
    model_name="product.template"
)
```

### 3. Test Current Behavior

```bash
# Run tests before changes
uv run test-all

# Save test results
uv run test-stats > pre-refactor-tests.txt
```

## Safe Refactoring Patterns

### Incremental Changes

```python
# DON'T: Change everything at once
# DO: Change incrementally

# Step 1: Refactor one file
MultiEdit(
    file_path="models/product.py",
    edits=[refactoring_edits]
)

# Step 2: Test that file
test_result = Bash("uv run test-unit")

# Step 3: Only continue if tests pass
if test_result.success:
    # Continue with next file
    pass
else:
    # Revert and investigate
    Bash("git checkout models/product.py")
```

### Validation Functions

```python
def safe_string_replace(file_path, old, new):
    """Replace with validation."""
    content = Read(file_path)
    
    # Check pattern exists
    if old not in content:
        raise ValueError(f"Pattern '{old}' not found in {file_path}")
    
    # Check replacement won't break syntax
    test_content = content.replace(old, new, 1)
    try:
        compile(test_content, file_path, 'exec')
    except SyntaxError as e:
        raise ValueError(f"Replacement would cause syntax error: {e}")
    
    # Perform replacement
    return MultiEdit(
        file_path=file_path,
        edits=[{"old_string": old, "new_string": new, "replace_all": True}]
    )
```

### Dependency Checking

```python
def check_method_dependencies(model, old_method, new_method):
    """Ensure method rename won't break dependencies."""
    
    # Find all calls to the method
    calls = mcp__odoo-intelligence__search_code(
        pattern=f"\\.{old_method}\\(",
        file_type="py"
    )
    
    # Find super() calls
    super_calls = mcp__odoo-intelligence__search_code(
        pattern=f"super\\(\\)\\.{old_method}\\(",
        file_type="py"
    )
    
    # Find XML references
    xml_refs = mcp__odoo-intelligence__search_code(
        pattern=f'name="{old_method}"',
        file_type="xml"
    )
    
    return {
        "python_calls": len(calls),
        "super_calls": len(super_calls),
        "xml_references": len(xml_refs),
        "total_impact": len(calls) + len(super_calls) + len(xml_refs)
    }
```

## Common Pitfalls

### 1. Breaking Inheritance

```python
# DANGER: Changing method signatures
# OLD:
def create(self, vals):
    return super().create(vals)

# NEW:
def create(self, vals_list):  # Different parameter name!
    return super().create(vals_list)

# SAFE: Keep compatible signatures
def create(self, vals):
    # Handle both single dict and list of dicts
    if isinstance(vals, dict):
        vals = [vals]
    return super().create(vals)
```

### 2. Breaking API Compatibility

```python
# DANGER: Removing public methods
# Check if method is used externally
external_usage = mcp__odoo-intelligence__search_code(
    pattern="env\\['model.name'\\]\\.method_name",
    file_type="py"
)

if external_usage:
    # Add deprecation instead of removing
    def old_method(self):
        warnings.warn(
            "old_method is deprecated, use new_method",
            DeprecationWarning
        )
        return self.new_method()
```

### 3. Breaking Views

```python
# Before removing/renaming fields
view_usage = mcp__odoo-intelligence__view_model_usage(
    model_name="product.template"
)

# Check if field is used in views
for field in fields_to_remove:
    if field in view_usage['fields_in_views']:
        print(f"WARNING: {field} is used in views!")
```

## Recovery Procedures

### Quick Rollback

```bash
# If tests fail after refactoring
git stash  # Save any uncommitted work
git checkout main  # Return to safe state
```

### Partial Rollback

```python
# Revert specific file
Bash("git checkout HEAD -- models/product.py")

# Revert specific changes
MultiEdit(
    file_path="models/product.py",
    edits=[
        {"old_string": new_pattern, "new_string": old_pattern, "replace_all": True}
    ]
)
```

### Investigation Tools

```python
# Find what broke
def investigate_failure(error_message):
    # Check recent changes
    recent = Bash("git diff HEAD")
    
    # Search for error pattern
    error_location = mcp__odoo-intelligence__search_code(
        pattern=error_message[:50],
        file_type="py"
    )
    
    # Check logs
    logs = mcp__odoo-intelligence__odoo_logs(lines=500)
    
    return {
        "changes": recent,
        "error_locations": error_location,
        "recent_logs": logs
    }
```

## Post-Refactoring Validation

### Comprehensive Testing

```bash
# 1. Syntax validation
python -m compileall addons/

# 2. Import validation
docker exec ${ODOO_PROJECT_NAME}-script-runner-1 /odoo/odoo-bin \
  -u product_connect --stop-after-init

# 3. Unit tests
uv run test-all

# 4. UI tests
uv run test-tour
```

### Performance Validation

```python
# Ensure refactoring didn't hurt performance
before_metrics = Read("pre-refactor-metrics.json")
after_metrics = mcp__odoo-intelligence__analysis_query(
    analysis_type="performance",
    model_name="product.template"
)

# Compare key metrics
for metric in ['query_count', 'response_time', 'memory_usage']:
    if after_metrics[metric] > before_metrics[metric] * 1.1:
        print(f"WARNING: {metric} increased by >10%")
```
