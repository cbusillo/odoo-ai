---
title: Coolify Operations
---


Purpose

- Document how to fetch logs and environment variables from Coolify-managed apps.

When to Use

- Debugging dev/testing environments deployed via Coolify.
- Verifying app-level environment variables and build settings.

Applies To

- Coolify-managed environments (OPW dev/testing, CM dev/testing).

Inputs/Outputs

- Inputs: COOLIFY_HOST, COOLIFY_TOKEN, app UUID
- Outputs: application logs, environment variable list, basic app metadata

API Quickstart

- List apps (UUIDs + branches):

```bash
curl -sk -H "Authorization: Bearer $COOLIFY_TOKEN" \
  https://$COOLIFY_HOST/api/v1/applications | jq -r '.[] | "\(.name)\t\(.uuid)\t\(.git_branch)"'
```

- Fetch logs (last 400 lines):

```bash
curl -sk -H "Authorization: Bearer $COOLIFY_TOKEN" \
  "https://$COOLIFY_HOST/api/v1/applications/<uuid>/logs?lines=400" | jq -r '.logs'
```

- Fetch env vars:

```bash
curl -sk -H "Authorization: Bearer $COOLIFY_TOKEN" \
  https://$COOLIFY_HOST/api/v1/applications/<uuid>/envs | jq -r '.[] | "\(.key)=\(.value)"'
```

Notes

- Prefer Coolify shared variables (team/project) for values reused across apps.
  Keep env-specific secrets on the app or environment level.
- Keep project- or environment-specific details in
  `docs/tooling/coolify.local.md` (gitignored).
- Do not target production unless explicitly instructed.

References

- @docs/ARCHITECTURE.md#runtime-topology
- @docs/tooling/docker.md#docker-usage

Maintainers

- Platform/DevOps

Last Updated

- 2025-12-25
