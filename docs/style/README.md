# Style Guide Index

Domain-specific style guides for efficient agent context management.

## Files

- **[CORE.md](CORE.md)** - Universal rules that apply to all development
    - Tool hierarchy, naming conventions, git practices
    - **Used by**: All agents, especially Refactor agent

- **[PYTHON.md](PYTHON.md)** - Python-specific coding standards
    - Type hints, f-strings, field definitions, control flow
    - **Used by**: Inspector agent, any Python-focused work

- **[JAVASCRIPT.md](JAVASCRIPT.md)** - JavaScript patterns for Odoo 18
    - No semicolons, Owl.js 2.0, no jQuery, component structure
    - **Used by**: Owl agent, frontend development

- **[TESTING.md](TESTING.md)** - Test-specific patterns and rules
    - SKU validation, base classes, mocking, tour patterns
    - **Used by**: Scout agent, test-related work

- **[ODOO.md](ODOO.md)** - Odoo-specific development patterns
    - Field naming, context usage, container paths, trust rules
    - **Used by**: Archer agent, Odoo research and patterns

## Benefits

- **60-75% token reduction** per agent interaction
- **Focused context**: Each agent gets only relevant rules
- **Complete coverage**: All original style rules preserved
- **Better maintainability**: Domain changes affect only relevant files

## Usage

Agents automatically reference the appropriate style files based on their specialization. No need to manually specify -
the agent documentation handles the references.