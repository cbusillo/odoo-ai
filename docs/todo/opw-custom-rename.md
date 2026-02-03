---
title: OPW Rename + Shared Addons Migration Plan
---


Status: in progress — rename/extractions done; pre-migration rename handled in
base hook; external_ids migration implemented; Shopify + motors split
confirmed; local restore completes; tests migration done; validation pending.

Goal: rename the legacy OPW addon to `opw_custom`, extract shared logic into
standalone addons, and migrate legacy Shopify/eBay IDs into `external_ids`.
No shim module.

## Requirements

- Legacy OPW addon renamed to `opw_custom`.
- Shared addons live in `addons/` with neutral names (e.g.,
  `environment_banner`, `external_ids`).
- OPW-specific addons follow `opw_*` naming pattern.
- Prefer smaller, focused addons (mirrors `cm_*` style).
- Migrate tests into the correct addon(s).
- Migrate Shopify/eBay IDs to `external_ids`.
- Full audit of repo references plus local env files and Coolify env keys.

## Key decisions (current)

- Consolidate to a single `shopify` system for IDs; use URL templates with
  `base_url` overrides for admin vs store links.
- `external_ids` needs a URL-template base override (implemented as
  `external.system.url.base_url`).
- No shim module.
- Shopify sync is an independent shared addon (`shopify_sync`), no OPW-only
  wrapper planned.
- Motors system is an independent shared addon (`marine_motors`).

## Candidates for extraction

- Shopify sync: shared first-class addon (`shopify_sync`) (done).
- Motors system: shared addon (`marine_motors`) (done).
- OPW-only Shopify extensions: none planned.

## Migration plan

1) Inventory and classify `product_connect`
   - OPW-specific -> `opw_custom` or `opw_*`
   - Shared -> standalone addons with neutral names

2) Rename module (done)
   - `git mv addons/product_connect addons/opw_custom`
   - Update manifests, assets, and imports
   - Update references in other addons/tests/docs

3) Extract shared addons (done)
   - `git mv` shared code into new addon(s)
   - Update asset bundles and dependencies

4) External IDs migration (implemented; validation pending; docs/todo/external_ids_migration.md)
   - res.partner: `shopify_customer_id`, `shopify_address_id`, `ebay_username`
   - product.product: `shopify_product_id`, `shopify_variant_id`,
     `shopify_condition_id`, `shopify_ebay_category_id`
   - product.image: `shopify_media_id`
   - Use `external.id` with `system_id` + `resource`
   - Use a single `shopify` system with `external.system.url.base_url` per
     template for admin/store
   - Align `resource` with URL template resources (`customer`, `product`)
   - URL templates to use (see `addons/external_ids/data/external_systems.xml`):
     - Shopify admin: `customer_admin`, `product_admin`
     - Shopify store: `product_store`
     - eBay: `profile`
   - Replace computed URL fields with `external.system.url` templates (codes above)
   - `shopify_sync` post-init hook migrates legacy columns into `external.id`
     and drops the legacy columns after seeding when safe

5) Data migration scripts
   - Pre-upgrade (required when no shim module; OpenUpgrade pre-migration):
     - `addons/openupgrade_scripts_custom/scripts/base/19.0.1.0/pre-migration.py`
       renames `ir_module_module.name` to `opw_custom` and reassigns moved XML IDs
       to extracted addons to prevent inconsistent module states when
       `product_connect` no longer has a manifest.
     - note: `addons/opw_custom/migrations/*` will not run until after the DB rename
   - Post-upgrade:
     - `addons/openupgrade_scripts_custom/scripts/opw_custom/19.0.8.2/post-migration.py`
       handles missing-manifest cleanup in the OpenUpgrade pass.
     - legacy ID fields already migrate in `shopify_sync` post-init hook
     - no separate legacy-field cleanup (columns dropped after seeding)

6) Tests migration (done)
   - Move unit/integration/tours into the owning addon
   - Update any test fixtures and asset includes
   - Transaction mixin unit coverage moved to `transaction_utilities`

7) Full audit (done)
   - Repo: `rg product_connect` only in this doc, the base OpenUpgrade pre-migration
     script, and generated Shopify gql headers (do not edit)
   - Local env files: `docker/config/*-local.env`, `.env`, `.env.example` clean
   - Coolify env keys: `uv run ops coolify env-get --apps opw-dev,opw-testing,opw-prod`
     returned no `product_connect` matches

8) Validation (in progress)
   - `uv run ops local upgrade-restart opw` (done 2026-01-28)
   - Verify assets via `?debug=assets` (HTTP 200 on `/web/login?debug=assets`, 2026-01-28)
   - Smoke test key flows and migrated tests (pending)
   - Full `uv run test run --json --stack opw --detached` completed 2026-01-28
     (session `test-20260128_003110`): unit/js pass; integration/tour reported
     0 tests and returned rc=1 (investigate missing tests)
   - Full `uv run test run --json --stack opw --detached` completed 2026-01-28
     (session `test-20260128_010712`): integration pass; unit error + tour
     failures traced to discuss_record_links domain bug (fixed)
   - Targeted reruns: `uv run test unit --modules discuss_record_links --stack opw`
     (session `test-20260128_095857`) and `uv run test tour --modules
     discuss_record_links,test_web_tours --stack opw` (session
     `test-20260128_095921`) both green
   - Full `uv run test run --json --stack opw --detached` completed 2026-01-28
     (session `test-20260128_101451`): unit/js/integration pass; tour failure
     in `test_web_tours` readiness check (fixed)
   - Targeted rerun: `uv run test tour --modules test_web_tours --stack opw`
     (session `test-20260128_103553`) green

## Risks / edge cases

- XML IDs break if `ir_model_data.module` is not migrated correctly.
- Shopify GIDs may need relaxed `id_format` if stored as-is.
- References may exist in env keys or server actions even if code refs are gone.
- Local resets now archive + remove Shopify external IDs when `test_store=True`
  to avoid unique constraint conflicts if the store changes.
- Remove `shopify_sync` post-init migration hook after opw-prod upgrade once
  legacy columns are fully retired.

## Open questions (resolved)

- Shopify stays independent in `shopify_sync` (no `opw_shopify_*` wrappers).
- Motors stays independent in `marine_motors`.
