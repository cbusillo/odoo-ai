# Temporary Files Directory

This directory holds temporary project artifacts so the repo root stays clean.

## Directory Structure

```text
tmp/
├── logs/           # Ad-hoc command logs and captured command output
├── test-logs/      # Test runner output (created automatically)
├── scripts/        # Temporary analysis and utility scripts (create on demand)
├── data/           # Scratch data extracts (create on demand)
└── README.md       # This file
```

## Purpose

The `tmp/` directory is used for:

1. **Logs** (`logs/`)
   - Captured output from long-running or noisy commands
   - Keep command output here instead of streaming large logs in-session

2. **Test Results** (`test-logs/`)
   - Output from `uv run test *` (see `docs/TESTING.md`)
   - Testkit writes the latest summaries under `tmp/test-logs/latest/` when a
     session exists
   - Older runs may be kept briefly for comparison, then pruned

3. **Temporary Scripts** (`scripts/`)
   - One-off analysis scripts and verification utilities
   - Long-running experiments that would otherwise require heredocs
   - Execute with `uv run python tmp/scripts/<name>.py`

4. **Temporary Data** (`data/`)
   - Export/import staging
   - Local analysis results or generated fixtures

## Important Notes

- **This directory is gitignored** - Nothing here will be committed
- **Clean regularly** - Delete old logs, caches, and test runs to save space
- **No production code** - Only temporary files belong here
- **Local-only scratch docs** - Use `docs/internal/todo/` for private notes you
  want to keep between sessions; use `docs/todo/` only for notes you intend to
  keep in the shared tracked docs set

## Cleanup

Typical cleanup:

```bash
# Remove generated logs and cached test output
rm -rf tmp/logs/* tmp/test-logs/*

# Remove cached Python bytecode from tmp scripts
find tmp/scripts -type d -name '__pycache__' -prune -exec rm -rf {} +
```

## Why tmp/ instead of /tmp?

- **Accessibility**: Agents can access local paths more reliably than system /tmp
- **Project scope**: Keeps temporary files within the project directory
- **Portability**: Works consistently across different systems
- **Visibility**: Easy to see and manage temporary files
