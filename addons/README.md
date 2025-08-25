# Addon Management Guide

This directory contains Odoo addons managed as git submodules. This approach provides version control, independent development, and easy sharing across projects.

## Current Addons

- **`disable_odoo_online`** - Disables Odoo online features (recommended for all projects)
- **`product_connect`** - Example addon demonstrating advanced patterns (e-commerce, Shopify integration)

## Managing Your Addons

### Adding Your Own Addon

1. **Create your addon repository**
   ```bash
   # In a separate location
   mkdir my-custom-addon
   cd my-custom-addon
   git init
   # Develop your addon...
   git remote add origin https://github.com/yourusername/my-custom-addon
   git push -u origin main
   ```

2. **Add it as a submodule to your fork**
   ```bash
   cd odoo-ai  # Your fork
   git submodule add https://github.com/yourusername/my-custom-addon addons/my_custom_addon
   git add .gitmodules addons/my_custom_addon
   git commit -m "Add my custom addon"
   git push
   ```

### Removing an Addon

To remove an addon you don't need (e.g., the example `product_connect`):

```bash
git submodule deinit addons/product_connect
git rm addons/product_connect
git commit -m "Remove product_connect example addon"
```

### Updating Addon Versions

To update a specific addon to its latest version:

```bash
cd addons/my_custom_addon
git pull origin main
cd ../..
git add addons/my_custom_addon
git commit -m "Update my_custom_addon to latest version"
```

### Working with Private Addons

For private addon repositories, use SSH URLs:

```bash
git submodule add git@github.com:company/private-addon addons/private_addon
```

Configure deploy keys or SSH access for your CI/CD pipeline.

## Cloning the Project

When cloning a project with submodules:

```bash
# Clone with submodules
git clone --recursive https://github.com/yourusername/odoo-ai

# Or if already cloned
git submodule update --init --recursive
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
└── CLAUDE.md        # Optional: Addon-specific AI context
```

## AI Context for Addons

Each addon can have its own `CLAUDE.md` file that will be automatically picked up by Claude Code. This allows addon-specific instructions and context without polluting the main project.

Example `addons/my_addon/CLAUDE.md`:
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

# Your addon submodules remain unchanged
git push origin main
```

## Best Practices

1. **Version Control**: Tag stable versions of your addons
2. **Documentation**: Include README.md in each addon
3. **Testing**: Write tests for your addons (see docs/TESTING.md)
4. **CI/CD**: Addon repos can have their own GitHub Actions for deployment
5. **Dependencies**: Document addon dependencies in `__manifest__.py`

## Alternative: Docker Volumes

If submodules are too complex, you can mount addons via Docker volumes:

```yaml
# docker-compose.override.yml
services:
  web:
    volumes:
      - ../my-addons:/opt/project/custom_addons
```

Then update your `.env`:
```bash
ODOO_ADDONS_PATH=/opt/project/custom_addons,/opt/project/addons,/odoo/addons,/volumes/enterprise
```

This approach is simpler but doesn't provide version control integration.