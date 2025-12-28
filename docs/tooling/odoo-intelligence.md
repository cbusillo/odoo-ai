---
title: Odoo Intelligence Tools
---


Why use them first

- Open a managed Odoo environment without crafting `docker exec` heredocs.
- Built-in helpers cover model discovery, field metadata, and ORM-powered read/writes.
- Responses stream back as structured JSON, which keeps prompts short and repeatable.

Recommended tool order

1. **Use odoo-intelligence helpers** (`model_query`, `field_query`, `analysis_query`, `execute_code`) for anything that
   can be expressed through the ORM.
2. **Drop into `odoo-bin shell`** only when you need interactivity or large exploratory scripts.
3. **Fallback to raw `docker exec` / SQL** solely for emergency debugging (schema corruption, ORM boot failures).

Common commands

- Inspect a model schema: `odoo-intelligence__model_query(operation="info", model_name="res.users")`.
- Search records by domain: `odoo-intelligence__execute_code` with a short snippet that runs via the ORM.
- Review inheritance/overrides: `odoo-intelligence__model_query(operation="inherit", pattern="stock.picking" )`.

Example – audit GPT service users

```python
odoo-intelligence__execute_code {
    "code": """
from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry

registry = Registry('opw')
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    data = {}
    for login in ('gpt', 'gpt-admin'):
        user = env['res.users'].search([('login', '=', login)], limit=1)
        data[login] = None if not user else {
            'id': user.id,
            'groups': user.groups_id.mapped('display_name'),
            'api_keys': user.api_key_ids.mapped('name'),
        }
print(data)
"""
}
```

Outputs arrive as JSON, making it easy to spot missing groups (`[]`) or absent users (`null`) without leaving the Codex
session.

Container management helpers

- `odoo-intelligence__odoo_status(verbose=true)` reports the compose containers that belong to the project and whether
  they are running; if the database container is stopped it now triggers a compose-backed autostart before reporting
  failure.
- `odoo-intelligence__odoo_restart(services="web-1")` (or `database-1`, `script-runner-1`, …) wraps `docker restart` with retry
  logic and will start the container when it is currently stopped.
