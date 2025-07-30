# Python Style Rules

Python-specific coding standards and patterns.

## Type Hints

- **Use built-in types**: `list`, `dict`, `set` instead of `List`, `Dict`, `Set` from typing
- **Use union operator**: `str | None` instead of `Optional[str]`
- **Avoid unnecessary imports**: Prefer fewer imports when the result is the same
- **Never use `Any` or `object`**: Be specific with types
- **Use Odoo Plugin types**: `odoo.model.product_template`, `odoo.values.product_template`

## String Formatting

- **Always use f-strings**: Even for logging and exceptions
- **No % formatting or .format()**: F-strings only

## Comments and Documentation

- **NO comments or docstrings**: Code should be self-documenting through:
    - Descriptive names using full words (no abbreviations)
    - Clear function/variable names that state their purpose
    - Method chains that read like sentences
- **Exception**: Comments allowed in config files when not clear what something does or why it's set to a value

## Control Flow

- **Early returns preferred**: No else after return
- **Ignore ruff rule TRY300**: Early returns are our preference

## Field Definitions

- **String attributes**: Omit `string` attribute when the display text should match the field name
    - **Python fields**: `processed_today = fields.Boolean()` displays as "Processed Today"
    - Odoo automatically converts underscores to spaces and capitalizes appropriately
    - This ensures consistency and reduces duplication
    - Use explicit `string` only when display text differs from name: `qty = fields.Integer(string="Quantity")`

## File Organization

- **Model tests**: Model tests go in `tests/`
- **Service tests**: Service-layer tests go in `services/tests/`
- **Temporary files**: Use prefixes `test_*` or `temp_*` in project root

## Common Python Patterns

### Fix Examples

**Import Errors:**

```python
# Before
from ..models.product import ProductTemplate  # Error if path wrong

# After  
from odoo.addons.product_connect.models.product_template import ProductTemplate
```

**Type Hints:**

```python
# Before
from typing import Optional, List, Dict
def method(self, vals: Optional[Dict]) -> List[str]:

# After
def method(self, vals: dict | None) -> list[str]:
```

**Field Definitions:**

```python
# Before
name = fields.Char(string="Product Name")  # Redundant string

# After
name = fields.Char()  # Auto-generates "Name" label
```