---
title: TODO / Optimization Ideas
---


## Optimize Motor Product Generation (create_motor_products)

- Profile product template matching and creation loops; consider batched create
  calls and prefetching related records.
- Avoid repeated name_search/read_group calls; fetch once per run.
- Consider server-side job queue if generation exceeds ~30–60s on typical
  datasets.
- Add progress bus events to update UI while processing.

## Stack Migration (OPW)

- Draft OPW prod cutover checklist and validate the prod gate.
- Create `opw_custom` addon as OPW prime layer; migrate OPW-only logic from
  `product_connect` over time.
- OPW testing-prod readiness:
  - Run JetBrains inspections on changed scope + git scope.
  - Human click-through and integration testing on `opw-testing`.
  - Schedule a 2-day cutover window once testing sign-off is complete.
  - During cutover: restore new `opw-prod` from `opw-prod.shiny`, verify, then
    move `odoo.outboardpartswarehouse.com` to the new host.
  - After cutover: block restore tooling on live prod (guard env + script).
