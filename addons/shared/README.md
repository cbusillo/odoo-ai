# Shared Addons

Purpose

- Hold reusable cross-client addons shared by tenant wrappers and
  tenant-specific addon buckets.

Rules

- Shared addons must not depend on tenant-specific addons.
- If a client addon becomes reusable, promote it here.
- Keep tenant wrappers at the addon root (`addons/<client>_custom/`) and keep
  tenant-specific supporting addons under their client bucket.
