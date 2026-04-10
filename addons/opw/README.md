# OPW Addons

Purpose

- Hold OPW-specific supporting addons that sit behind the thin `opw_custom`
  tenant entrypoint addon.

Rules

- Addons here may depend on `addons/shared/` modules.
- Addons here should not be imported from shared addons.
- Keep `opw_custom` thin and move reusable logic into `addons/shared/` when it
  stops being OPW-specific.
