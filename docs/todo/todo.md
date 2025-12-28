Title: TODO / Optimization Ideas

- Optimize motor product generation (create_motor_products):
  - Profile product template matching and creation loops; consider batched
    create calls and prefetching related.
  - Avoid repeated name_search/read_group calls; fetch once per run.
  - Consider server-side job queue if generation exceeds ~30–60s on typical datasets.
  - Add progress bus events to update UI while processing.

- Coolify rollout cleanup:
  - Decide whether to use Coolify shared variables for build-time values
    (GITHUB_TOKEN, ODOO_ENTERPRISE_REPOSITORY, ODOO_ADDON_REPOSITORIES).
  - Add Docker Hub login on the Coolify build host to avoid pull stalls.
  - Verify cm-testing stability (restart loops) and capture root cause.
  - Prune uv scripts that are no longer used (keep restore/sanitize/init helpers).

- DX cleanup + workflow hardening:
  - Decide auto-deploy triggers for dev/testing vs manual prod promotion.

- Completed (recent):
  - Swept stale docs/scripts after monorepo shift; removed/updated.
  - Added one-button restore/init wrappers (dev/testing).
  - Added prod deploy gate workflow + CLI (backup/list/rollback).
