# CM Addons

Purpose

- Hold CellMechanic-specific supporting addons that sit behind the thin
  `cm_custom` tenant entrypoint addon.

Rules

- Addons here may depend on `addons/shared/` modules.
- Addons here should not be imported from shared addons.
- Keep `cm_custom` thin; move reusable logic into `addons/shared/` when it
  stops being CM-specific.
