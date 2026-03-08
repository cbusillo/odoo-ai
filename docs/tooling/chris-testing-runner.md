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
  - `actions.runner.cbusillo-odoo-enterprise-docker.chris-testing-odoo-enterprise-docker.service`
  - `actions.runner.cbusillo-odoo-enterprise-docker.chris-testing-odoo-enterprise-docker-2.service`
  - `actions.runner.cbusillo-odoo-enterprise-docker.chris-testing-odoo-enterprise-docker-3.service`

Cache model

- `odoo-docker` and `odoo-enterprise-docker` workflows use ephemeral Buildx
  builders and `type=gha` cache.
- Local BuildKit state should not accumulate between runs.

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

- Use only when Buildx artifacts leak and consume space.
- Commands:

  ```bash
  ssh chris-testing 'docker ps -a --format "{{.Names}}" \
  | grep "^buildx_buildkit_builder-" \
  | xargs -r docker rm -f'
  ssh chris-testing 'docker volume ls --format "{{.Name}}" \
  | grep "^buildx_buildkit_builder-.*_state$" \
  | xargs -r docker volume rm'
  ssh chris-testing 'docker image prune -f'
  ```

Notes

- If CI fails with transient `type=gha` cache transport errors, rerun the
  workflow before changing runner config.
