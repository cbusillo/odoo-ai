# Core Style Rules

Universal rules that apply to all agents and development work.

## Tool Hierarchy (CRITICAL)

**ALWAYS follow this order**:

1. **MCP Tools FIRST** - Project-wide, instant results
2. **Built-in Tools SECOND** - File operations
3. **Bash LAST RESORT** - Only when no MCP exists

**NEVER use Bash for**: `find`, `grep`, `cat`, `ls`, `docker ps`, `docker logs`

## Naming Conventions

- **Full words**: `calculate_total_amount` not `calc_tot_amt`
- **Descriptive**: Variable and function names should describe what they do
- **Boolean fields**: Use `is_` or `has_` prefix
- **Constants**: UPPER_SNAKE_CASE
- **Private methods**: Single underscore prefix `_method_name`

## Git Best Practices

### File Operations

- **Always use `git mv`**: Never use regular `mv` command
    - ✅ `git mv old_file.py new_file.py` - Preserves Git history
    - ❌ `mv old_file.py new_file.py` - Breaks Git history tracking
    - **Why**: Git history tracking is critical for debugging, blame functionality, and understanding code evolution
    - **Impact**: Without `git mv`, you lose the ability to trace changes across file renames, making debugging much
      harder

### Refactoring with Git History

- **When renaming files**: Always use `git mv` even for multiple operations
  ```bash
  # ✅ RIGHT: Preserves complete history
  git mv models/old_name.py models/new_name.py
  git mv views/old_name.xml views/new_name.xml
  
  # ❌ WRONG: Creates new files with no history
  mv models/old_name.py models/new_name.py
  mv views/old_name.xml views/new_name.xml
  ```

- **Mass refactoring**: Use git-aware tools or scripts that preserve history
- **Directory restructuring**: Move directories with `git mv` to maintain history of all contained files

### Commit Practices

- **Never commit unless asked**: User controls when to commit
- **File organization**: Keep related files together, follow existing directory structure
- **Commit scope**: Each commit should represent a single logical change

## Line Length

- **Python**: 133 characters max
- **Markdown**: No limit, but be reasonable

## Common Mistakes to Avoid

1. Creating files unnecessarily - always prefer editing existing files
2. Creating documentation proactively - only create docs when requested
3. Using emojis - avoid unless explicitly requested
4. Long explanations - be concise, answer directly
5. Using generic tutorials - follow project-specific patterns

## Development Workflow

- **Never run Python files directly**: Always use proper Odoo environment
- **Temporary files**: Use the project `tmp/` directory structure:
    - `tmp/scripts/` - One-off analysis and utility scripts
    - `tmp/tests/` - Test runner output and test files
    - `tmp/data/` - Export files and analysis results
    - See `tmp/README.md` for complete structure and guidelines
- **Incremental changes**: Make small, focused changes rather than large refactors

This file contains only the universal rules that all agents need to know.