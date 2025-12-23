# Stack Matrix (WIP)

## Front-matter

- Title: Stack Matrix (WIP)
- Purpose: Keep a small map of site+environment to stack name, env files, and
  addon manifest so deploy/restore targets are obvious.
- When to Use: Adding a new stack, verifying a deploy target before pushing, or
  updating addon pins for a stack.
- Applies To: `deploy`, `restore-from-upstream`, stack helper commands, OPW/CM.
- Inputs/Outputs: Input = stack name (e.g., `opw-local`), env chain, addon
  manifest. Output = resolved compose files, merged env, pinned addon refs.
- References: @docs/workflows/multi-project.md, @docs/tooling/docker.md
- Maintainers: Core maintainers
- Last Updated: 2025-12-23

Stack Matrix

- `opw-local` → `docker/config/opw-local.env`, manifest `docker/config/opw-local.addons.json`
- `opw-testing` → `docker/config/opw-testing.env`, manifest `docker/config/opw-testing.addons.json`
- `opw-prod` → `docker/config/opw-prod.env`, manifest `docker/config/opw-prod.addons.json`
- `cm-local` → `docker/config/cm-local.env`, manifest `docker/config/cm-local.addons.json`
- `cm-testing` → `docker/config/cm-testing.env`, manifest `docker/config/cm-testing.addons.json`
- `cm-prod` → `docker/config/cm-prod.env`, manifest `docker/config/cm-prod.addons.json`

Manifest Format

- JSON to avoid extra deps; path is relative to repo root.

Example (`docker/config/opw-local.addons.json`)

{
  "schema_version": "1.0",
  "addons": {
    "product_connect": {
      "path": "addons/product_connect",
      "ref": "HEAD"
    },
    "cm_custom": {
      "path": "addons/cm_custom",
      "ref": "HEAD"
    }
  }
}

Preflight Verification

- Set `STACK_VERIFY=1` (or `DEPLOY_STACK_VERIFY=1`) in a stack env file to make
  `deploy` and `restore-from-upstream` run `stack verify` before doing anything.
