# Development Patches

This directory contains minimal patches applied during the development Docker build to fix known Odoo issues.

## fix_dev_mode_validation.patch

**Issue**: When running Odoo with `--dev all`, the account module's `action_view_partner_with_same_bank` button causes a
validation error because its name resolves to `False` during early XML validation.

**Error**: `Invalid xmlid False for button of type action.`

**Root Cause**: The button has `type="object"` and `name="action_view_partner_with_same_bank"`, but during --dev mode
validation, the view is processed before Python models are loaded, causing the name to resolve to `False` instead of the
actual method name.

**Solution**: This patch adds a check in `ir_ui_view.py` to skip validation for buttons with `False` names, with a
warning log to track when this occurs. This ensures we don't hide legitimate configuration errors while working around
the loading order issue.

**Applied**: Only in development builds via Dockerfile

**Removal**: Once Odoo fixes this upstream, simply delete this patch file and remove the COPY/RUN lines from the
Dockerfile. The warning logs will help identify when the issue is fixed upstream.
