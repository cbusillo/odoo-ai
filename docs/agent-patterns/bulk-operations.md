# Refactor Bulk Operations Guide

Patterns and techniques for large-scale refactoring.

## MultiEdit Patterns

### Field Definition Cleanup

```python
# Remove all redundant string attributes
MultiEdit(
    file_path="models/product_template.py",
    edits=[
        {"old_string": 'string="Name"', "new_string": "", "replace_all": True},
        {"old_string": 'string="Description"', "new_string": "", "replace_all": True},
        {"old_string": 'string="Price"', "new_string": "", "replace_all": True},
        {"old_string": 'string="Cost"', "new_string": "", "replace_all": True},
        {"old_string": 'string="Active"', "new_string": "", "replace_all": True},
    ]
)
```

### Type Hint Modernization

```python
# Update all type hints to modern syntax
MultiEdit(
    file_path="services/shopify/client.py",
    edits=[
        {"old_string": "Optional[str]", "new_string": "str | None", "replace_all": True},
        {"old_string": "Optional[int]", "new_string": "int | None", "replace_all": True},
        {"old_string": "Optional[float]", "new_string": "float | None", "replace_all": True},
        {"old_string": "Optional[bool]", "new_string": "bool | None", "replace_all": True},
        {"old_string": "Optional[dict]", "new_string": "dict | None", "replace_all": True},
        {"old_string": "Optional[list]", "new_string": "list | None", "replace_all": True},
        {"old_string": "List[str]", "new_string": "list[str]", "replace_all": True},
        {"old_string": "Dict[str, Any]", "new_string": "dict[str, Any]", "replace_all": True},
        {"old_string": "Tuple[", "new_string": "tuple[", "replace_all": True},
        {"old_string": "Set[", "new_string": "set[", "replace_all": True},
    ]
)
```

### Import Cleanup

```python
# Remove unnecessary typing imports
MultiEdit(
    file_path="models/base.py",
    edits=[
        {"old_string": "from typing import Optional, List, Dict, Tuple, Set\n", "new_string": "", "replace_all": False},
        {"old_string": "from typing import Optional\n", "new_string": "", "replace_all": False},
        {"old_string": "from typing import List\n", "new_string": "", "replace_all": False},
        {"old_string": "from typing import Dict\n", "new_string": "", "replace_all": False},
    ]
)
```

### String Formatting Updates

```python
# Convert old string formatting to f-strings
MultiEdit(
    file_path="models/motor_product.py",
    edits=[
        {"old_string": '"Product %s" % self.name', "new_string": 'f"Product {self.name}"', "replace_all": True},
        {"old_string": '"Error: %s" % e', "new_string": 'f"Error: {e}"', "replace_all": True},
        {"old_string": '"{} - {}".format(self.name, self.year)', "new_string": 'f"{self.name} - {self.year}"', "replace_all": True},
    ]
)
```

## Batch File Processing

### Process Multiple Files

```python
# Find all Python files
files = Glob(pattern="**/*.py")

# Filter to models only
model_files = [f for f in files if "/models/" in f]

# Apply same refactoring to each
for file in model_files:
    MultiEdit(
        file_path=file,
        edits=[
            {"old_string": "_logger.debug", "new_string": "_logger.info", "replace_all": True},
            {"old_string": "print(", "new_string": "_logger.info(", "replace_all": True},
        ]
    )
```

### Coordinated Multi-File Changes

```python
# Example: Rename a method across codebase
# Step 1: Find all usages
usages = mcp__odoo-intelligence__find_method(method_name="old_method_name")

# Step 2: Update each file
for model in usages:
    file_path = f"models/{model.replace('.', '_')}.py"
    MultiEdit(
        file_path=file_path,
        edits=[
            {"old_string": "def old_method_name(", "new_string": "def new_method_name(", "replace_all": True},
            {"old_string": "self.old_method_name(", "new_string": "self.new_method_name(", "replace_all": True},
            {"old_string": "super().old_method_name(", "new_string": "super().new_method_name(", "replace_all": True},
        ]
    )
```

## Complex Pattern Replacement

### Regex-Based Refactoring

```python
# When simple string replacement isn't enough
import re

content = Read("models/product.py")

# Replace complex patterns
new_content = re.sub(
    r'fields\.Char\(string="([^"]+)"\)',
    r'fields.Char()',  # Remove all string attributes
    content
)

Write("models/product.py", new_content)
```

### AST-Based Refactoring

```python
# For structural changes
import ast

# Parse Python code
tree = ast.parse(content)

# Modify AST
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        # Add decorator
        if not any(d.id == 'api.model' for d in node.decorator_list):
            node.decorator_list.append(ast.Name(id='api.model'))

# Convert back to code
new_content = ast.unparse(tree)
```

## Safety Checks

### Pre-refactoring Validation

```python
# Before bulk changes
def validate_refactoring(file_path, old_pattern, new_pattern):
    content = Read(file_path)
    occurrences = content.count(old_pattern)
    
    if occurrences == 0:
        print(f"Warning: Pattern not found in {file_path}")
        return False
    elif occurrences > 100:
        print(f"Warning: {occurrences} occurrences - verify this is correct")
        return confirm_large_change()
    
    return True
```

### Post-refactoring Testing

```python
# After changes
def test_refactoring():
    # Run syntax check
    result = Bash("python -m py_compile models/*.py")
    
    # Run unit tests
    test_result = Bash("uv run test-unit")
    
    # Check for import errors
    import_check = mcp__odoo-intelligence__odoo_update_module(
        modules="product_connect",
        force_install=False
    )
    
    return all([result.success, test_result.success, import_check.success])
```