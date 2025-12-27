# Addon Management Guide

This directory contains Odoo addons managed directly in this repo (no submodules). This keeps shared code and
deployment tooling in one place while still letting you isolate client-specific addons by directory.

## Current Addons

- **`product_connect`** - Example addon demonstrating advanced patterns (e-commerce, Shopify integration)

Private addons (not stored in this repo) are pulled during build using
`ODOO_PRIVATE_ADDON_REPOSITORIES`.

## Adding Your Own Addon

1. Create a new addon folder under `addons/`.
2. Add the standard Odoo structure (`__manifest__.py`, `models/`, `views/`, etc.).
3. Commit the new files in this repo.

```bash
mkdir -p addons/my_custom_addon
touch addons/my_custom_addon/__init__.py addons/my_custom_addon/__manifest__.py
git add addons/my_custom_addon
git commit -m "Add my_custom_addon"
```

## Removing an Addon

```bash
rm -rf addons/my_custom_addon
git add -A
git commit -m "Remove my_custom_addon"
```

## Sharing Addons Externally

If an addon needs to be shared outside this repo, mirror or export it from this repo instead of embedding a submodule.
Keep the monorepo as the source of truth.

## Cloning the Project

No submodules are required:

```bash
git clone https://github.com/yourusername/odoo-ai
```

## Addon Structure

Each addon should follow Odoo's standard structure:

```
my_addon/
├── __init__.py
├── __manifest__.py
├── models/
├── views/
├── security/
├── data/
├── static/
├── tests/
└── AGENTS.md        # Addon-specific notes for LLM agents (design, tests)
```

## Addon Notes (Agent‑Focused)

Each addon should include a short `AGENTS.md` with focused guidance for LLM agents (implementation hints, test entry
points, and links). Keep it small and link to project docs by handle instead of copying content.

Example `addons/my_addon/AGENTS.md`:

```markdown
# My Addon Context

This addon handles [specific business logic].

## Key Patterns

- Pattern 1: [Description]
- Pattern 2: [Description]

## Testing

Run tests with: `uv run test-unit my_addon`
```

## Syncing with Upstream

When you need to sync your fork with the original odoo-ai repository:

```bash
# Add upstream remote (one time)
git remote add upstream https://github.com/original/odoo-ai

# Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

## Best Practices

1. **Version Control**: Tag stable versions of your addons
2. **Documentation**: Include README.md in each addon
3. **Testing**: Write tests for your addons (see docs/testing.md)
4. **Dependencies**: Document addon dependencies in `__manifest__.py`
