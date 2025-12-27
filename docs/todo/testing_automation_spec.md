# Dev & Testing Automation (Future)

Status: deferred (stale spec).

We currently deploy dev/testing via **Coolify**. The previous GitHub Actions
spec that pushed to a legacy host is no longer aligned with the active flow
and has been removed to reduce noise.

If we revisit CI/CD automation, prefer one of:

- Coolify API triggers (deploy by app UUID).
- A dedicated build pipeline that publishes images and lets Coolify pull tags.

Reference: @docs/todo/NEW_ARCH.md
