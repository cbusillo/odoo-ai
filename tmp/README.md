# Temporary Files Directory

This directory contains all temporary files for the project, keeping the root directory clean and organized.

## Directory Structure

```
tmp/
├── tests/          # Test runner output files
├── scripts/        # Temporary analysis and utility scripts  
├── data/           # Temporary data files
└── README.md       # This file
```

## Purpose

The `tmp/` directory is used for:

1. **Test Results** (`tests/`)
   - Output from `tools/test_runner.py`
   - Each test run creates a timestamped subdirectory
   - Contains logs, summaries, and progress tracking files
   - Example: `tmp/tests/odoo-tests-20250204_143022/`

2. **Temporary Scripts** (`scripts/`)
   - One-off analysis scripts
   - Testing utilities
   - GPT integration tests
   - Any script that doesn't belong in the main codebase

3. **Temporary Data** (`data/`)
   - Export files
   - Import staging
   - Analysis results
   - Any data files that shouldn't be committed

## Important Notes

- **This directory is gitignored** - Nothing here will be committed
- **Safe for Claude/AI agents** - Can read/write without system restrictions
- **Clean regularly** - Delete old test results to save disk space
- **No production code** - Only temporary/test files belong here

## Cleanup

To clean old test results:
```bash
# Remove test results older than 7 days
find tmp/tests -type d -name "odoo-tests-*" -mtime +7 -exec rm -rf {} +

# Remove all test results
rm -rf tmp/tests/odoo-tests-*
```

## Why tmp/ instead of /tmp?

- **Accessibility**: Claude and other tools can access local paths more reliably than system /tmp
- **Project scope**: Keeps temporary files within the project directory
- **Portability**: Works consistently across different systems
- **Visibility**: Easy to see and manage temporary files