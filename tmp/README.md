# Temporary Files Directory

This directory contains all temporary files for the project, keeping the root directory clean and organized.

## Directory Structure

```text
tmp/
├── test-logs/      # Test runner output (created automatically)
├── scripts/        # Temporary analysis and utility scripts (create on demand)
├── data/           # Scratch data extracts (create on demand)
└── README.md       # This file
```

## Purpose

The `tmp/` directory is used for:

1. **Test Results** (`test-logs/`)
   - Output from `uv run test *` (see `docs/TESTING.md`)
   - Testkit keeps the latest JSON summaries under `tmp/test-logs/latest/`
   - Older runs live in timestamped folders for diffing or provenance

2. **Temporary Scripts** (`scripts/`)
   - One-off analysis scripts and verification utilities
   - Long-running experiments that would otherwise require heredocs
   - Create the directory when you first need it: `mkdir -p tmp/scripts`
   - Execute with `uv run python tmp/scripts/<name>.py` (respects the sandbox bypass rules)

3. **Temporary Data** (`data/`)
   - Export/import staging
   - Local analysis results or generated fixtures
   - Create with `mkdir -p tmp/data` as needed

## Important Notes

- **This directory is gitignored** - Nothing here will be committed
- **Safe for AI agents** - Can read/write without system restrictions
- **Clean regularly** - Delete old test results to save disk space
- **No production code** - Only temporary/test files belong here
- **Local TODOs / longer notes** - Use `docs/todo/` (gitignored) for scratch docs you want to keep between sessions

## Cleanup

To clean old test results:

```bash
# Remove test results older than 7 days
find tmp/tests -type d -name "odoo-tests-*" -mtime +7 -exec rm -rf {} +

# Remove all test results
rm -rf tmp/tests/odoo-tests-*
```

## Why tmp/ instead of /tmp?

- **Accessibility**: Agents can access local paths more reliably than system /tmp
- **Project scope**: Keeps temporary files within the project directory
- **Portability**: Works consistently across different systems
- **Visibility**: Easy to see and manage temporary files
