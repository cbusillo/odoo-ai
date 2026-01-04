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
