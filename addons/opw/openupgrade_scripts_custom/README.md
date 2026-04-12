# OpenUpgrade Custom Scripts

This folder hosts custom OpenUpgrade migration scripts for OPW.

- This package now lives under `addons/opw/` because it is OPW-specific and
  temporary, not part of the long-term shared-addon boundary.
- The restore pipeline points OPENUPGRADE_SCRIPTS_PATH here.
- Add module-specific migration steps under scripts/<module_name>/.
- Keep scripts minimal and targeted; document changes in docs/todo/odoo-upgrade-19.md.
- Retire this package once OPW production is fully promoted onto Odoo 19 and no
  OpenUpgrade path is still needed.
