# TODO / Optimization Ideas

- Optimize motor product generation (create_motor_products):
  - Profile product template matching and creation loops; consider batched
    create calls and prefetching related.
  - Avoid repeated name_search/read_group calls; fetch once per run.
  - Consider server-side job queue if generation exceeds ~30–60s on typical datasets.
  - Add progress bus events to update UI while processing.

- Coolify rollout cleanup:
  - Move shared env vars into Coolify shared variables (PYTHON_VERSION,
    ODOO_VERSION, COMPOSE_BUILD_TARGET, ODOO_ADDONS_PATH,
    ODOO_ENTERPRISE_REPOSITORY, ODOO_UPDATE, GITHUB_TOKEN).
  - Update NEW_ARCH.md to reflect Coolify-based deploy flow and remove legacy notes.
  - Prune uv scripts that are no longer used (keep restore/sanitize/init helpers).
