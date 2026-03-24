---
title: PostgreSQL Tuning for Parallel Test Runs
---

Purpose

- Enable high parallelism (dozens of Odoo test containers) without the DB
  becoming the bottleneck.

When

- When running large parallel test grids.

Recommended docker-compose override (server profile):

```yaml
# docker-compose.override.yml (server)
services:
  database:
    command:
      - postgres
      - -c
      - max_connections=500
      - -c
      - shared_buffers=2GB
      - -c
      - effective_cache_size=6GB
      - -c
      - maintenance_work_mem=1GB
      - -c
      - checkpoint_completion_target=0.9
      - -c
      - wal_buffers=16MB
      - -c
      - work_mem=64MB
      - -c
      - wal_level=replica
```

Notes

- Adjust memory values to your host RAM (above assumes 32–64GB).
- Ensure the Docker host has sufficient IOPS; consider local NVMe or tmpfs for CI scratch.
- For extreme parallelism (>50 containers), consider a connection pooler (e.g., pgbouncer) in transaction pooling mode.
- The shared stack defaults also expose `POSTGRES_MAX_FILES_PER_PROCESS` and
  `POSTGRES_ULIMIT_NOFILE_SOFT` / `POSTGRES_ULIMIT_NOFILE_HARD` for the
  `database` service in `docker-compose.yml`; Dokploy-managed targets inherit
  those values from the compose file they deploy.

Verifications

- `docker compose exec database psql -U $ODOO_DB_USER -c "SHOW max_connections;"`
- Monitor with `docker compose logs -f database` for FATAL: too many connections.
