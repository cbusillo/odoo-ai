# Multi-Project Configuration (Local Dev)

This guide covers running multiple isolated stacks locally (OPW + Cell Mechanic)
using layered Docker Compose configs. Remote environments are managed in
Coolify and do not use the overlays in `docker/config/`.

## Local stacks

| Stack       | Purpose      | Ports           | Config source   |
|-------------|--------------|-----------------|-----------------|
| `opw-local` | OPW dev      | 8069/8072/15432 | `opw-local.env` |
| `cm-local`  | CM isolation | 9069/9072/9432  | `cm-local.env`  |

## Quick flow

1. Create the stack env file (untracked):

   ```bash
   cp docker/config/opw-local.env.example docker/config/opw-local.env
   ```

2. Start the stack:

   ```bash
   uv run deploy deploy --stack opw-local
   ```

3. (Optional) Restore upstream data:

   ```bash
   uv run restore-from-upstream --stack opw-local
   ```

## Notes

- Layer order and env merge rules are documented in `docker/config/README.md`.
- Use unique `ODOO_STATE_ROOT` per stack to avoid sharing filestore/postgres.
- Switch stacks by stopping one (`uv run deploy deploy --stack cm-local --down`)
  before starting the other.
