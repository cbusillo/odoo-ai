# Style Guide Index

Domain-specific style guides for efficient development and agent context management.

## Style Files

- **[docs/style/CORE.md](style/CORE.md)** - Universal rules (tool hierarchy, naming, git practices)
- **[docs/style/PYTHON.md](style/PYTHON.md)** - Python patterns (type hints, f-strings, field definitions)
- **[docs/style/JAVASCRIPT.md](style/JAVASCRIPT.md)** - JavaScript patterns (no semicolons, Owl.js, no jQuery)
- **[docs/style/TESTING.md](style/TESTING.md)** - Test patterns (SKU validation, base classes, mocking)
- **[docs/style/ODOO.md](style/ODOO.md)** - Odoo patterns (field naming, context usage, container paths)

## Agent Usage

Each agent references only relevant style files for focused context:

- **Inspector Agent** → All style files (comprehensive quality checking)
- **Scout Agent** → TESTING.md (test patterns)
- **Owl Agent** → JAVASCRIPT.md (frontend patterns)
- **Refactor Agent** → CORE.md (universal consistency)
- **Archer Agent** → ODOO.md (Odoo research patterns)