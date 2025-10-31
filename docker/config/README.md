# Docker Config Layering

#

# This directory now supports layered configuration so the shared repo can host

# multiple customer stacks (for example **opw** and **cm**) without copying large

# env files around. Environment variables are merged by the deploy tooling and

# Compose overlays are stacked in a predictable order.

## Layer order

### Environment files

# When `uv run deploy` (and future bootstrap tooling) loads a stack it reads

# environment variables in the following order. Later files override earlier

# values.

```
.env → docker/config/base.env → docker/config/{project}.env → docker/config/{project}-{variant}.env
```

# Example for `opw-local`:

```
.env → base.env → opw.env → opw-local.env
```

# Only the `*.env.example` templates are tracked. Copy the ones you need, fill in

# real values, and keep the resulting `*.env` files out of git (`*.env*` remains

# ignored in the root `.gitignore`).

### Compose overlays

# Compose files are stacked from most generic to most specific:

```
docker-compose.yml
→ docker-compose.override.yml
→ docker/config/base.yaml
→ docker/config/{project}.yaml
→ docker/config/{project}-{variant}.yaml
→ optional extras (e.g. docker/config/_restore_ssh_volume.yaml)
```

# The `DEPLOY_COMPOSE_FILES` entries in the stack env files follow the same

# ordering so ad-hoc `docker compose` calls behave the same as the deploy CLI.

## Template quick start

1. Copy the shared templates

   ```bash
   cp docker/config/base.env.example docker/config/base.env
   cp docker/config/opw.env.example docker/config/opw.env        # or cm.env
   cp docker/config/opw-local.env.example docker/config/opw-local.env
   ```

2. Fill in real values (database credentials, Shopify keys, etc.).

3. Run the stack with either the deploy CLI or plain Compose, for example:

   ```bash
   export DEPLOY_COMPOSE_FILES="docker/config/_restore_ssh_volume.yaml:docker/config/base.yaml:docker/config/opw.yaml:docker/config/opw-local.yaml"
   docker compose $(printf ' -f %s' ${DEPLOY_COMPOSE_FILES//:/ -f }) up
   ```

## Provided templates

| Scope    | File(s)                                  | Notes                                    |
|----------|------------------------------------------|------------------------------------------|
| Shared   | `base.env.example`, `base.yaml`          | Defaults that apply to every stack       |
| OPW      | `opw.env.example`, `opw.yaml`            | Customer-specific defaults               |
| CM       | `cm.env.example`, `cm.yaml`              | Customer-specific defaults               |
| Variants | `opw-local/dev/testing.env.example`, etc | Port mappings & remote paths per variant |

# Only the `.example` files are tracked. The real `.env` files should contain

# secrets and **must remain untracked**.

## Stack cheat sheet

| Stack         | Env files (in order)                             | Compose files (in order)                                                                         |
|---------------|--------------------------------------------------|--------------------------------------------------------------------------------------------------|
| `opw-local`   | `.env`, `base.env`, `opw.env`, `opw-local.env`   | `docker-compose.yml`, `docker-compose.override.yml`, `base.yaml`, `opw.yaml`, `opw-local.yaml`   |
| `opw-dev`     | `.env`, `base.env`, `opw.env`, `opw-dev.env`     | `docker-compose.yml`, `docker-compose.override.yml`, `base.yaml`, `opw.yaml`, `opw-dev.yaml`     |
| `opw-testing` | `.env`, `base.env`, `opw.env`, `opw-testing.env` | `docker-compose.yml`, `docker-compose.override.yml`, `base.yaml`, `opw.yaml`, `opw-testing.yaml` |
| `cm-local`    | `.env`, `base.env`, `cm.env`, `cm-local.env`     | `docker-compose.yml`, `docker-compose.override.yml`, `base.yaml`, `cm.yaml`, `cm-local.yaml`     |

## Security reminders

- Keep real credentials in untracked `.env` files.
- Review `git status` before committing to ensure secrets are not staged.
- Shopify tokens in the examples are blank on purpose—fill them in locally.
- Remote stacks should continue to use dedicated SSH keys (`id_restore_opw`).

## Extending

- To add a new customer project, copy `opw.env.example`/`opw.yaml` to new
  files, adjust variables, and create variant templates following the same
  naming pattern.
- To add a new variant (e.g. staging), copy one of the existing
  `{project}-{variant}.env.example` and `{project}-{variant}.yaml` pairs and
  adjust the host-specific values.

