---
title: Codex Workflow
---


Working Loop

1) Plan: define smallest next change and acceptance.
2) Patch: minimal diffs only.
3) Inspect: scope=changed → scope=git before commit.
4) Test: unit/js scoped to touched modules.
5) Iterate: repeat until clean.
6) Gate: full inspection + `uv run test run --json`.

Notes

- Use separate Codex sessions for analysis vs implementation to keep context lean; pass document handles, not content.
