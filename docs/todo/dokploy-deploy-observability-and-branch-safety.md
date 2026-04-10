---
title: Dokploy Deploy Observability and Branch Safety
---

Purpose

- Track durable follow-up work for Dokploy deployment safety, diagnostics, and
  operator ergonomics.

Status

- Added on 2026-03-24.
- Triggered by repeated Dokploy compose deploy failures that returned only
  deployment status and id without actionable error detail.

Problems Observed

- `platform ship` force-pushes the managed target branch before it knows
  whether Dokploy can deploy the selected ref.
- Failed compose deployments currently report only deployment id and status,
  even when deployment metadata includes fields such as `log_path`, `title`,
  and `description`.
- `platform dokploy logs` exposes deployment metadata but does not surface the
  actual failure detail operators need during incident response.
- Current docs recommend clean worktrees plus `--source-ref HEAD`, but do not
  clearly call out the branch-mutation risk when the downstream deploy fails.

Recommended Follow-ups

- [ ] Make `platform ship` branch-safe for Dokploy-managed targets.
  Preferred direction: when branch sync updates a managed target branch and the
  subsequent Dokploy deploy fails, automatically restore the branch to the
  previously recorded remote commit unless an explicit override says to keep the
  failed ref in place.
- [ ] Enrich failed deployment output from `platform ship`.
  Include target name, deployment id, created timestamp, `log_path`, and
  Dokploy `errorMessage` when available.
- [ ] Expand `platform dokploy logs` to expose all failure metadata already
  present in Dokploy API responses, especially `errorMessage`, and provide a
  clearer operator path to the relevant deployment log.
- [ ] Update Dokploy operator docs to explain the branch-sync failure mode and
  the safest workflow for surgical deployment tests.
- [ ] Add regression coverage for failed compose deployments.
  Cover branch restore behavior, richer failure output, and `platform dokploy
  logs` metadata rendering.

Suggested Implementation Order

1. Branch restore on failed `platform ship` deploys.
2. Better deploy failure messages and metadata capture.
3. `platform dokploy logs` output improvements.
4. Docs and regression tests.

Relevant Code

- `tools/platform/commands_release.py`
- `tools/platform/dokploy.py`
- `tools/platform/commands_dokploy.py`
- `tools/platform/cli.py`

Relevant Docs

- `docs/tooling/platform-cli.md`
- `docs/tooling/platform-command-patterns.md`
- `docs/tooling/dokploy.md`
- `docs/roles.md`
