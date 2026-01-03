---
title: Runtime Baselines
---

Purpose

- Avoid hardcoding runtime versions in prose; point at source config.

When

- When updating Python/runtime baselines or CI/tooling assumptions.

Python

- Minimum supported Python version: `pyproject.toml` → `requires-python`.
- Container/runtime Python version: `docker-compose.yml` → `PYTHON_VERSION` and
  `docker/Dockerfile` → `ARG PYTHON_VERSION`.

When updating Python, keep these sources consistent (and update CI/tooling that
assumes a specific version).
