Title: Dev & Testing Automation (GitHub Actions)
Purpose: Describe the GitHub Actions-driven workflow that builds, tests, and deploys Odoo 18 Enterprise containers to docker.shiny for the dev/testing environments.
When to Use: Setting up or auditing CI/CD for non-production Odoo stacks.
Applies To: Platform/Ops maintainers.
Inputs/Outputs: Inputs — Git pushes to `main`/`testing`, secrets from GH environment store; Outputs — tagged container images, docker compose deploys, health-check logs.
References: @docs/todo/NEW_ARCH.md
Maintainers: Platform Team
Last Updated: 2025-10-01

## Summary

- GitHub Actions is the single automation surface. No on-host webhook receiver or queue.
- Each push to `main` (dev) or `testing` (test) triggers a build job followed by a gated deploy job.
- Builds run on a self-hosted runner with access to Odoo Enterprise sources via BuildKit secrets.
- Deploys SSH into docker.shiny, render `.env` from secrets, run `docker compose pull/up`, execute module upgrades, and curl a health endpoint.
- Rollbacks are handled by redeploying a retained image tag through `workflow_dispatch`.

## Components

### GitHub Actions workflow (`.github/workflows/deploy.yml`)

Environment-specific secrets are stored using GitHub Environments:

```
DEV:
  ODOO_ENTERPRISE_SSH_KEY
  ODOO_ENV_FILE            # base64 or heredoc for .env
  DOCKER_SHINY_SSH_KEY
  REGISTRY_TOKEN

TESTING:
  ... (same keys)
```

Workflow outline:

```yaml
on:
  push:
    branches: [main, testing]
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [dev, testing]
      image_tag:
        description: Override tag for rollback

jobs:
  build:
    runs-on: self-hosted
    steps:
      - checkout
      - setup-buildx
      - fetch-enterprise (ssh agent + git clone)
      - run-tests
      - docker build (web/script-runner, --secret)
      - docker push ghcr.io/<org>/odoo:${{ github.ref_name }}-${{ github.sha }}
      - echo image digest to job output

  deploy:
    needs: build
    runs-on: self-hosted
    environment: ${{ github.ref_name == 'main' && 'DEV' || 'TESTING' }}
    steps:
      - write .env from ${{ secrets.ODOO_ENV_FILE }}
      - ssh docker.shiny "docker login ghcr.io ..."
      - ssh docker.shiny "IMAGE_TAG=${{ needs.build.outputs.image }} docker compose -f docker-compose.yml -f environments/${{ env_name }}.yaml pull web script-runner"
      - ssh docker.shiny "... up -d --remove-orphans"
      - ssh docker.shiny "docker compose exec script-runner /odoo/odoo-bin -u $ODOO_UPDATE -d $ODOO_DB_NAME --stop-after-init"
      - ssh docker.shiny "curl -sf http://localhost:<port>/web/health"
      - ssh docker.shiny "echo '<timestamp>|<env>|<tag>|<sha>' >> /opt/odoo-ai/releases.log"
```

### docker.shiny prerequisites

- Docker Engine + Compose plugin installed.
- Self-hosted GitHub runner registered (with Docker socket access) to execute the workflow.
- `/opt/odoo-ai/` directory structured per @docs/todo/NEW_ARCH.md, including `environments/dev.yaml` etc.
- Pre-login to GHCR (or chosen registry) using a PAT with `write:packages` and `read:packages` scopes.

---

## Deploy Flow Details

1. **Build**
   - Git checkout, clone enterprise into build context.
   - Run test suite.
   - Build images with BuildKit secrets and tag `ghcr.io/<org>/odoo:<env>-<sha>`.
   - Push images and export digest.

2. **Deploy**
   - Determine environment from branch or manual input.
   - Render `.env` file on docker.shiny (base64 decode + chmod 600).
   - Pull the new image tags.
   - Run `docker compose up -d` with environment overlay.
   - Execute module upgrade in container.
   - Health check via `/web/health`; failure aborts and reports.
   - Append deploy info to `releases.log`.

3. **Rollback/Promotion**
   - Use `workflow_dispatch` with `image_tag` pointing to a previous digest or promotion target.
   - Deploy job re-runs with supplied tag, following the same steps.

---

## Monitoring & Alerting

- GitHub Actions job results serve as the primary audit trail.
- Optional: push health check result to Slack/Teams via workflow notification step.
- External uptime checker can monitor `/web/health` endpoints.

---

## Implementation Checklist

1. Register self-hosted runner on docker.shiny (`runs-on: self-hosted, labels: [docker-shiny]`).
2. Configure GH Environments (DEV, TESTING) with required secrets.
3. Implement `/web/health` endpoint in Odoo returning 200.
4. Author `docker-compose.yml` + environment overlays under `environments/`.
5. Create `.github/workflows/deploy.yml` following the outline above.
6. Test deploy flow on a feature branch pointing at a staging namespace in the registry.
7. Document rollback steps in runbook (`releases.log` usage, `workflow_dispatch`).

This spec supersedes the legacy webhook receiver/worker plan and aligns with the
clean-sheet architecture in @docs/todo/NEW_ARCH.md.
