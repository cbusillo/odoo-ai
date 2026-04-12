---
title: Chris Testing Runner
---

Purpose

- Document operations for the `chris-testing` self-hosted GitHub runner.

When

- When CI builds fail on runner capacity, disk pressure, or Docker state drift.

Runner layout

- Hostname: `chris-testing`
- Runners are installed under `/opt/actions-runners/`.
- Active services:
    - `actions.runner.cbusillo-odoo-docker.chris-testing-odoo-docker.service`
    - `actions.runner.cbusillo-odoo-docker.chris-testing-odoo-docker-2.service`
    - `actions.runner.cbusillo-odoo-docker.chris-testing-odoo-docker-3.service`
    - three additional private Enterprise-layer runner services are present but
      intentionally unnamed in this public doc

Cache model

- `odoo-docker` publish workflows now use persistent per-runner Buildx builders
  named `odoo-docker-publish-<runner>` with `keep-state=true` and
  `cleanup=false`.
- Verification jobs still use ephemeral Buildx builders plus `type=gha` cache.
- Publish jobs keep GHCR registry cache as a fallback and prune publish cache
  entries older than 14 days after each run.

Health checks

- Host disk:
  `ssh chris-testing 'df -h /'`
- Docker footprint:
  `ssh chris-testing 'docker system df'`
- Leaked Buildx builder artifacts:

    ```bash
    ssh chris-testing 'docker ps -a --format "{{.Names}}" \
    | grep -c "^buildx_buildkit_builder-" || true'
    ssh chris-testing 'docker volume ls --format "{{.Name}}" \
    | grep -c "^buildx_buildkit_builder-.*_state$" || true'
    ```

- Persistent publish builder disk usage:

    ```bash
    ssh chris-testing 'docker buildx ls --format "{{.Builder.Name}}" \
    | grep "^odoo-docker-publish-" \
    | sort -u \
    | while IFS= read -r builder_name; do
        docker buildx du --builder "$builder_name" --verbose || true
      done'
    ```

Hygiene timer

- Installed files:
    - `/usr/local/sbin/chris-testing-docker-hygiene.sh`
    - `/etc/systemd/system/chris-testing-docker-hygiene.service`
    - `/etc/systemd/system/chris-testing-docker-hygiene.timer`
- Schedule: `03:00` and `15:00` local time (with a randomized 15-minute delay).
- Action: `docker image prune -f --filter dangling=true`

Service commands

```bash
ssh chris-testing 'systemctl status chris-testing-docker-hygiene.timer --no-pager'
ssh chris-testing 'journalctl -u chris-testing-docker-hygiene.service \
-n 100 --no-pager'
ssh chris-testing 'systemctl start chris-testing-docker-hygiene.service'
```

Emergency cleanup

- Use only when Buildx artifacts leak or a persistent publish builder needs a
  hard reset.
- For a single persistent builder reset, set `builder_name` to the affected
  runner, for example `odoo-docker-publish-chris-testing-odoo-docker-2`.
- Commands:

    ```bash
    builder_name="${builder_name:?set builder_name to the affected runner, e.g. odoo-docker-publish-chris-testing-odoo-docker-2}"
    ssh chris-testing 'docker ps -a --format "{{.Names}}" \
    | grep "^buildx_buildkit_builder-" \
    | xargs -r docker rm -f'
    ssh chris-testing 'docker volume ls --format "{{.Name}}" \
    | grep "^buildx_buildkit_builder-.*_state$" \
    | xargs -r docker volume rm'
    ssh chris-testing "docker buildx rm --force \"${builder_name}\""
    ssh chris-testing 'docker image prune -f'
    ```

Notes

- If publish slows down unexpectedly, inspect the persistent builder before
  assuming remote cache drift; verify jobs can still hit transient `type=gha`
  transport errors independently of the publish path.
