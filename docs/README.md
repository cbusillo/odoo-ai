---
title: Project Documentation
---


Purpose

- Provide the routing map for project documentation.

When

- At the start of any task to pick the right handles.

Routing

- Start a change: [@docs/workflows/codex-workflow.md](workflows/codex-workflow.md)
- Workflow playbooks: [@docs/workflows/debugging.md](workflows/debugging.md),
  [@docs/workflows/refactor.md](workflows/refactor.md),
  [@docs/workflows/multi-project.md](workflows/multi-project.md),
  [@docs/workflows/prod-deploy.md](workflows/prod-deploy.md)
- Testing flow: [@docs/TESTING.md](TESTING.md)
- Testing commands: [@docs/tooling/testing-cli.md](tooling/testing-cli.md)
- Reviews and gate: [@docs/policies/acceptance-gate.md](policies/acceptance-gate.md),
  [@docs/tooling/inspection.md](tooling/inspection.md)
- Documentation style: [@docs/policies/doc-style.md](policies/doc-style.md)
- Odoo canon: [@docs/odoo/workflow.md](odoo/workflow.md), [@docs/odoo/orm.md](odoo/orm.md),
  [@docs/odoo/security.md](odoo/security.md), [@docs/odoo/performance.md](odoo/performance.md)
- Style: [@docs/style/index.md](style/index.md) (then [@docs/style/python.md](style/python.md),
  [@docs/style/javascript.md](style/javascript.md), [@docs/style/testing.md](style/testing.md),
  [@docs/style/browser-automation.md](style/browser-automation.md))
- Integrations: [@docs/integrations/README.md](integrations/README.md) (Shopify:
  [@docs/integrations/shopify.md](integrations/shopify.md),
  Authentik: [@docs/integrations/authentik.md](integrations/authentik.md),
  eBay: [@docs/integrations/ebay.md](integrations/ebay.md))
- Data sources: [@docs/data-sources/README.md](data-sources/README.md)
- Tooling: [@docs/tooling/codex-cli.md](tooling/codex-cli.md),
  [@docs/tooling/odoo-intelligence.md](tooling/odoo-intelligence.md),
  [@docs/tooling/platform-cli.md](tooling/platform-cli.md),
  [@docs/tooling/platform-command-patterns.md](tooling/platform-command-patterns.md),
  [@docs/tooling/secrets.md](tooling/secrets.md),
  [@docs/tooling/dokploy.md](tooling/dokploy.md),
  [@docs/tooling/gpt-service-user.md](tooling/gpt-service-user.md),
  [@docs/tooling/runtime-baselines.md](tooling/runtime-baselines.md),
  [@docs/tooling/db-tuning.md](tooling/db-tuning.md),
  [@docs/tooling/gate-benchmark.md](tooling/gate-benchmark.md),
  [@docs/tooling/image-contracts.md](tooling/image-contracts.md),
  [@docs/tooling/chris-testing-runner.md](tooling/chris-testing-runner.md),
  [@docs/tooling/docker.md](tooling/docker.md),
  [@docs/tooling/cm-seeds.md](tooling/cm-seeds.md)
- Architecture: [@docs/ARCHITECTURE.md](ARCHITECTURE.md), [@docs/resources.md](resources.md)
- Roles: [@docs/roles.md](roles.md)
- Platform migration status: [@docs/todo/platform-migration-status.md](todo/platform-migration-status.md)
- Odoo 19 OPW cutover: [@docs/todo/odoo-19-cutover-runbook.md](todo/odoo-19-cutover-runbook.md)

Notes

- Keep docs small; prefer linking by handle to larger guides when needed.
- `docs/internal/` is intentionally excluded from this index; it is a local,
  gitignored workspace for sensitive or instance-specific notes.
