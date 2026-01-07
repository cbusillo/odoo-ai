---
title: Odoo 19 Post-Upgrade Cleanup
---


Purpose

- Track cleanup tasks after the Odoo 19 production cutover so upgrade
  artifacts can be removed safely.

Context

- Current production: single Odoo 18 environment.
- Upgrade assets (OpenUpgrade addon + upgrade docs) remain until cutover is
  complete.

Plan (post-cutover)

- Create an Odoo 18 archive branch (example: `production-odoo18-archive`)
  for rollback reference.
- Remove the OpenUpgrade addon and related configuration from the repo once it
  is no longer needed.
- Remove upgrade-only docs: @docs/todo/odoo-upgrade-19.md,
  @docs/todo/odoo-upgrade-19-testing.md.
- Confirm restore tooling and local bootstrap no longer depend on OpenUpgrade
  assets after removal.

Notes

- Git history retains upgrade artifacts if recovery is ever required.
