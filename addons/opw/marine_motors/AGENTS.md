# AGENTS.md — marine_motors

Purpose

- Motor teardown workflows, tests, and reporting for marine inventory.

Key Points

- Keep motor-specific logic here; avoid Shopify or client-specific code.
- Label printing uses PrintNode and shared notification mixins.

Testing

- Unit: motor state transitions and test templates.
- Tours: motor workflow.

References

- @docs/odoo/performance.md
