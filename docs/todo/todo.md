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

## Local Env Hygiene

- Decide whether `ODOO_ADMIN_PASSWORD` should live only in `.env` (untracked)
  and remove it from `docker/config/cm-local.env`, or confirm the tracked local
  default is intentional.
