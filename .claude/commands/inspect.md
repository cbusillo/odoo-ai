---
description: Direct code quality analysis using Inspector agent
argument-hint: "[module_name|file_path]"
---

@docs/agents/inspector.md

Run direct code quality analysis using PyCharm inspections and project-wide tools.

Target: $ARGUMENTS (default: current file in editor)

Inspector provides technical analysis:

1. **PyCharm Inspections** (current files)
    - Import errors and type checking
    - Code style violations
    - Pattern detection

2. **Project-wide Analysis** (MCP tools)
    - Performance patterns across codebase
    - Field dependencies and relationships
    - Anti-pattern detection

3. **Detailed Reports**
    - Specific line-by-line issues
    - Severity classification
    - Fix recommendations

**Use Cases:**

- `inspect` - Analyze current file
- `inspect product_connect` - Analyze module
- `inspect specific/file.py` - Analyze specific file

For comprehensive quality coordination, use `/quality` instead.