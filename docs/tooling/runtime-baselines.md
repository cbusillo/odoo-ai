---
title: Runtime Baselines
---


This repo avoids hardcoding runtime versions in prose. Prefer pointing at the
configuration that actually controls the environment.

## Python

- Minimum supported Python version: `pyproject.toml` → `requires-python`.
- Container/runtime Python version: `docker-compose.yml` → `PYTHON_VERSION` and
  `docker/Dockerfile` → `ARG PYTHON_VERSION`.

When updating Python, keep these sources consistent (and update CI/tooling that
assumes a specific version).
