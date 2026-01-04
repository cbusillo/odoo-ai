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

## Coolify Rollout Cleanup

- Verify cm-testing stability (restart loops) and capture root cause.
- Prune uv scripts that are no longer used (keep restore/sanitize/init helpers).

## DX Cleanup + Workflow Hardening

- Decide auto-deploy triggers for dev/testing vs manual prod promotion.
