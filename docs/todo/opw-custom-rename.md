---
title: OPW Rename + Shared Addons Migration Plan
---


Status: draft — awaiting sequencing decisions.

Goal: rename `product_connect` to `opw_custom`, extract shared logic into
standalone addons, and migrate legacy Shopify/eBay IDs into `external_ids`.
No shim module.

## Requirements

- Rename `product_connect` to `opw_custom`.
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
- DM is also marine → motors become a strong shared-addon candidate.

## Candidates for extraction

- Shopify sync: shared first-class addon (`shopify_sync`).
- OPW-only extensions (if needed): `opw_shopify_<suffix>` as thin wrappers.
- Motors system: shared addon candidate now that OPW + DM are marine.

## Migration plan

1) Inventory and classify `product_connect`
   - OPW-specific -> `opw_custom` or `opw_*`
   - Shared -> standalone addons with neutral names

2) Rename module
   - `git mv addons/product_connect addons/opw_custom`
   - Update manifests, assets, and imports
   - Update references in other addons/tests/docs

3) Extract shared addons
   - `git mv` shared code into new addon(s)
   - Update asset bundles and dependencies

4) External IDs migration (per docs/todo/external_ids_migration.md)
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

5) Data migration scripts
   - Pre-upgrade (required when no shim module; run as SQL/OpenUpgrade pre-migration):
     - rename `ir_module_module.name` from `product_connect` -> `opw_custom`
     - update `ir_model_data.module` for renamed/moved XML IDs
     - note: `addons/opw_custom/migrations/*` will not run until after the DB rename
   - Post-upgrade (in `addons/opw_custom/migrations/*`):
     - migrate legacy ID fields into `external.id`
     - optionally clear legacy fields after verification

6) Tests migration
   - Move unit/integration/tours into the owning addon
   - Update any test fixtures and asset includes

7) Full audit
   - Repo: `rg product_connect` (code/docs/tests/data)
   - Local env files: `docker/config/*-local.env`
   - Coolify env keys for the relevant apps (values redacted unless `--show-values`;
     do not paste output into PRs/tickets/logs):
     `uv run ops coolify env-get --apps <comma-separated-apps>`
   - Replace any `product_connect` keys or references

8) Validation
   - `uv run ops local upgrade-restart opw`
   - Verify assets via `?debug=assets`
   - Smoke test key flows and migrated tests

## Risks / edge cases

- XML IDs break if `ir_model_data.module` is not migrated correctly.
- Shopify GIDs may need relaxed `id_format` if stored as-is.
- References may exist in env keys or server actions even if code refs are gone.

## Open questions

- For `shopify_sync`, what functionality should be in the shared addon, and what
  (if anything) should remain OPW-only in `opw_shopify_*` addons?
- Motors: should it be extracted as a shared addon now, or kept OPW-only (inside
  `opw_custom` or split into `opw_motors`)?
