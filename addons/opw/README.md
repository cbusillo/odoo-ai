# OPW Addons

Purpose

- Hold OPW-specific supporting addons that sit behind the thin `opw_custom`
  tenant entrypoint addon.

Examples

- Business-domain addons such as `marine_motors` live here while they remain
  OPW-only.
- Integration addons such as `shopify_sync` live here while they remain
  OPW-only.
- Temporary upgrade assets such as `openupgrade_scripts_custom` also belong
  here for the duration of the OPW Odoo 19 migration window.

Rules

- Addons here may depend on `addons/shared/` modules.
- Addons here should not be imported from shared addons.
- Keep `opw_custom` thin and move reusable logic into `addons/shared/` when it
  stops being OPW-specific.
