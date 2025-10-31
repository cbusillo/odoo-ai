# Multi-Project Configuration

This guide describes how to run multiple isolated Odoo projects (OPW, Cell Mechanic, etc.) side-by-side using layered
Docker Compose configurations.

## Layered Configuration Pattern

The deploy tooling uses a layered approach that lets you override and extend base configurations:

1. **Base layer** (`docker-compose.yml`) – Core service definitions, shared across all projects
2. **Override layer** (`docker-compose.override.yml`) – Local development defaults (ports, depends_on, etc.)
3. **Project layer** (`docker/config/{project}.yaml`) – Project-specific settings (env files, port offsets, project
   names)
4. **Variant layers** (optional) – Additional overlays (SSH mounts, testing-specific config, etc.)

Each layer can override or extend the previous layers. This approach keeps the base clean while allowing per-project
customization.

## Available Stacks

| Stack         | Purpose                    | Ports           | Compose Project | Config File        |
|---------------|----------------------------|-----------------|-----------------|--------------------|
| `opw-local`   | Main OPW development       | 8069/8072/5432  | `odoo`          | `opw-local.yaml`   |
| `opw-dev`     | Remote OPW dev environment | 28069/28072/... | `opw-dev`       | `opw-dev.yaml`     |
| `opw-testing` | Remote OPW testing         | 18069/18072/... | `opw-testing`   | `opw-testing.yaml` |
| `cm-local`    | Cell Mechanic isolation    | 9069/9072/9432  | `cm-local`      | `cm-local.yaml`    |

## Configuration Flow

### 1. Create Stack Environment File

Each stack needs a `.env` file under `docker/config/<stack>.env` (git-ignored):

```bash
# docker/config/cm-local.env example
COMPOSE_PROJECT_NAME=cm-local
ODOO_PROJECT_NAME=cm-local
ODOO_DB_NAME=cm
ODOO_STATE_ROOT=${HOME}/odoo-ai/cm-local
ODOO_UPDATE=cell_mechanic,external_ids
```

### 2. Specify Compose Files (Optional)

Control layering order via `DEPLOY_COMPOSE_FILES`:

```bash
# Explicit layering with restore SSH volume
DEPLOY_COMPOSE_FILES=docker-compose.yml:docker-compose.override.yml:docker/config/_restore_ssh_volume.yaml:docker/config/opw-testing.yaml
```

If omitted, the tooling uses the default pattern:

- `docker-compose.yml`
- `docker-compose.override.yml` (if exists)
- `docker/config/{stack-name}.yaml` (if exists)

### 3. Deploy the Stack

Use the deploy tooling to handle file ordering and environment merging:

```bash
# Initial deploy with build
uv run deploy deploy --stack cm-local --build

# Start/restart without rebuild
uv run deploy deploy --stack cm-local

# Stop the stack
uv run deploy deploy --stack cm-local --down
```

Or manually with `docker compose`:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker/config/cm-local.yaml \
  up -d
```

### 4. Restore Data (Optional)

If the stack needs upstream data:

```bash
uv run restore-from-upstream --stack cm-local
```

This creates the database, syncs the filestore, and applies `ODOO_UPDATE` modules.

## Project Layer Structure

Project YAML files (`docker/config/{project}.yaml`) typically:

1. Override the compose project name
2. Add project-specific env files
3. Publish host ports (if needed)
4. Set service dependencies

Example `cm-local.yaml`:

```yaml
name: ${COMPOSE_PROJECT_NAME:-cm-local}

services:
  web:
    env_file:
      - .env
      - docker/config/cm-local.env
    depends_on:
      - database
    ports:
      - "9069:8069"
      - "9072:8072"
  database:
    env_file:
      - .env
      - docker/config/cm-local.env
    ports:
      - "9432:5432"
  script-runner:
    env_file:
      - .env
      - docker/config/cm-local.env
    depends_on:
      - database
```

## Switching Between Projects

Each stack uses isolated:

- Docker Compose project names (container naming)
- State directories (`ODOO_STATE_ROOT`)
- Port bindings
- Database names

You can run multiple stacks simultaneously or switch between them:

```bash
# Stop current stack
uv run deploy deploy --stack opw-local --down

# Start different stack
uv run deploy deploy --stack cm-local
```

## Bind Mount Isolation

The `ODOO_STATE_ROOT` variable ensures each stack writes to its own directories:

```bash
${ODOO_STATE_ROOT}/
├── filestore/     # Odoo file attachments
├── postgres/      # PostgreSQL data
└── logs/          # Odoo logs
```

Default (if unset): `${HOME}/odoo-ai/${ODOO_PROJECT_NAME}/...`

Remote stacks should explicitly set `/opt/odoo-ai/data/<stack>`.

## Common Patterns

### Local Development Stack

Minimal config for local work:

```bash
# docker/config/my-project.env
ODOO_PROJECT_NAME=my-project
ODOO_DB_NAME=mydb
ODOO_STATE_ROOT=${HOME}/odoo-ai/my-project
ODOO_UPDATE=my_addon,base
```

### Testing/Staging Stack

Include SSH mounts for restore operations:

```bash
# docker/config/my-testing.env
ODOO_PROJECT_NAME=my-testing
ODOO_STATE_ROOT=/opt/odoo-ai/data/my-testing
DEPLOY_COMPOSE_FILES=docker-compose.yml:docker/config/_restore_ssh_volume.yaml:docker/config/my-testing.yaml
RESTORE_SSH_DIR=/root/.ssh
```

### Multi-Variant Stack

Layer multiple overlays:

```bash
DEPLOY_COMPOSE_FILES=docker-compose.yml:docker-compose.override.yml:docker/config/base-opw.yaml:docker/config/opw-testing.yaml:docker/config/_monitoring.yaml
```

## Troubleshooting

### Port Conflicts

If ports are occupied, adjust them in your project's YAML:

```yaml
services:
  web:
    ports:
      - "10069:8069"  # Use different host port
```

### Container Name Conflicts

Ensure `COMPOSE_PROJECT_NAME` is unique per stack:

```bash
COMPOSE_PROJECT_NAME=my-unique-stack
```

### Database Conflicts

Each stack should use its own `ODOO_DB_NAME`:

```bash
ODOO_DB_NAME=cm  # for cm-local
ODOO_DB_NAME=opw # for opw-local
```

## References

- Base compose configuration: `docker-compose.yml`
- Existing stack configs: `docker/config/*.yaml`
- Deploy tooling: `tools/deployer/cli.py`
- Restore script: `docker/scripts/restore_from_upstream.py`
- Docker usage: `docs/tooling/docker.md`
- Cell Mechanic recipe: `docs/recipes/cell-mechanic-db.md`
