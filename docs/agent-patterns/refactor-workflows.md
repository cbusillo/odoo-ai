# Refactor Complex Workflows

Multi-agent coordination patterns for large refactoring projects.

## Full Module Refactoring Workflow

### Phase 1: Analysis

```python
# 1. Quality analysis
quality_issues = Task(
    description="Find all quality issues",
    prompt="@docs/agents/inspector.md\n\nAnalyze product_connect module for all quality issues",
    subagent_type="inspector"
)

# 2. Pattern research  
patterns = Task(
    description="Find current patterns",
    prompt="@docs/agents/archer.md\n\nFind all deprecated patterns in use",
    subagent_type="archer"
)

# 3. Performance baseline
performance = Task(
    description="Baseline performance",
    prompt="@docs/agents/flash.md\n\nAnalyze current performance bottlenecks",
    subagent_type="flash"
)
```

### Phase 2: Planning

```python
# Create refactoring plan based on analysis
refactoring_plan = Task(
    description="Create refactoring plan",
    prompt=f"""@docs/agents/planner.md
    
Based on these findings:
- Quality issues: {quality_issues}
- Deprecated patterns: {patterns}
- Performance issues: {performance}

Create a comprehensive refactoring plan with priorities and dependencies.
""",
    subagent_type="planner"
)
```

### Phase 3: Execution

```python
# Execute refactoring in priority order
for task in refactoring_plan.tasks:
    if task.type == "frontend":
        Task(
            description=f"Refactor {task.target}",
            prompt=f"@docs/agents/owl.md\n\n{task.description}",
            subagent_type="owl"
        )
    elif task.type == "backend":
        # I handle backend refactoring
        execute_backend_refactoring(task)
    elif task.type == "tests":
        Task(
            description=f"Update tests for {task.target}",
            prompt=f"@docs/agents/scout.md\n\n{task.description}",
            subagent_type="scout"
        )
```

### Phase 4: Validation

```python
# Final quality check
final_check = Task(
    description="Validate refactoring",
    prompt="@docs/agents/inspector.md\n\nVerify all issues are resolved",
    subagent_type="inspector"
)
```

## Type Hint Modernization Workflow

### Step 1: Find All Type Hints

```python
# Research current usage
type_usage = Task(
    description="Find type hint patterns",
    prompt="""@docs/agents/archer.md

Find all files using:
- from typing import Optional, List, Dict
- Type hints with these imports
""",
    subagent_type="archer"
)
```

### Step 2: Systematic Update

```python
# Get list of files to update
files_to_update = type_usage.files

# Process in batches
batch_size = 10
for i in range(0, len(files_to_update), batch_size):
    batch = files_to_update[i:i+batch_size]
    
    # Update each file
    for file in batch:
        MultiEdit(
            file_path=file,
            edits=[
                # Remove imports
                {"old_string": "from typing import Optional, List, Dict, Tuple, Set\n", "new_string": ""},
                {"old_string": "from typing import Optional\n", "new_string": ""},
                # Update type hints
                {"old_string": "Optional[str]", "new_string": "str | None", "replace_all": True},
                {"old_string": "List[", "new_string": "list[", "replace_all": True},
                {"old_string": "Dict[", "new_string": "dict[", "replace_all": True},
            ]
        )
    
    # Test after each batch
    test_result = Bash("uv run test unit")
    if not test_result.success:
        print(f"Batch {i//batch_size} failed, investigating...")
        break
```

## Legacy Pattern Removal Workflow

### JavaScript/Frontend

```python
# 1. Find all legacy patterns
legacy_js = Task(
    description="Find legacy JS patterns",
    prompt="""@docs/agents/archer.md

Find all files with:
- odoo.define
- require()
- widget.extend
- jQuery usage
""",
    subagent_type="archer"
)

# 2. Modernize each component
for component in legacy_js.components:
    Task(
        description=f"Modernize {component}",
        prompt=f"""@docs/agents/owl.md

Convert this legacy component to Owl.js 2.0:
{component.code}

Requirements:
- Use ES6 modules
- Convert to Owl component
- Remove jQuery
- Update imports
""",
        subagent_type="owl"
    )
```

### Python/Backend

```python
# 1. Find old patterns
old_patterns = mcp__odoo-intelligence__search_code(
    pattern="api.multi|api.one|api.returns",
    file_type="py"
)

# 2. Update decorators
for file in old_patterns:
    MultiEdit(
        file_path=file,
        edits=[
            {"old_string": "@api.multi", "new_string": "", "replace_all": True},
            {"old_string": "@api.one", "new_string": "", "replace_all": True},
            {"old_string": "@api.returns", "new_string": "@api.model", "replace_all": True},
        ]
    )
```

## Cross-Module Refactoring

### Rename Model Field

```python
# Complex workflow for renaming a field used across modules

# 1. Find all usages
field_analysis = Task(
    description="Analyze field usage",
    prompt="""@docs/agents/archer.md

Find all usages of product.template.old_field_name:
- Python files
- XML views  
- JavaScript
- Domain filters
""",
    subagent_type="archer"
)

# 2. Create migration
migration_content = '''
def migrate(cr, version):
    cr.execute("""
        ALTER TABLE product_template 
        RENAME COLUMN old_field_name TO new_field_name
    """)
'''
Write("migrations/14.0.1.0.0/post-migration.py", migration_content)

# 3. Update Python files
for file in field_analysis.python_files:
    MultiEdit(
        file_path=file,
        edits=[
            {"old_string": "old_field_name", "new_string": "new_field_name", "replace_all": True}
        ]
    )

# 4. Update XML files
for file in field_analysis.xml_files:
    MultiEdit(
        file_path=file,
        edits=[
            {"old_string": 'name="old_field_name"', "new_string": 'name="new_field_name"', "replace_all": True},
            {"old_string": "'old_field_name'", "new_string": "'new_field_name'", "replace_all": True},
        ]
    )

# 5. Update JavaScript
for file in field_analysis.js_files:
    Task(
        description="Update field in JS",
        prompt=f"""@docs/agents/owl.md
        
Update field name from old_field_name to new_field_name in:
{file}
""",
        subagent_type="owl"
    )
```

## Continuous Refactoring Strategy

### Weekly Code Health Check

```python
def weekly_refactoring():
    # 1. Find new issues
    issues = Task(
        description="Weekly code check",
        prompt="@docs/agents/inspector.md\n\nFind new code quality issues this week",
        subagent_type="inspector"
    )
    
    # 2. Prioritize
    critical = [i for i in issues if i.severity == "high"]
    
    # 3. Fix critical issues
    for issue in critical[:5]:  # Limit to 5 per week
        fix_issue(issue)
    
    # 4. Update standards
    if new_pattern_found(issues):
        update_coding_standards()
```

### Incremental Modernization

```python
# Modernize one module per sprint
modules = ["product_connect", "motor_import", "shopify_sync"]

for module in modules:
    # Week 1: Analysis
    analyze_module(module)
    
    # Week 2: Refactor structure
    refactor_structure(module)
    
    # Week 3: Update patterns
    modernize_patterns(module)
    
    # Week 4: Test and document
    validate_module(module)
```
