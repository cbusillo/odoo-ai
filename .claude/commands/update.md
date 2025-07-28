---
description: Update Odoo modules
argument-hint: "<module_name> [--dev]"
tools: [mcp__odoo-intelligence__odoo_update_module, Bash]
---

Update module: $ARGUMENTS

If --dev flag is present, use:

```bash
!docker exec odoo-opw-script-runner-1 /odoo/odoo-bin -u $ARGUMENTS --stop-after-init --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise
```

Otherwise use MCP tool for simple updates.