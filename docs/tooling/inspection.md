---
title: Inspections (JetBrains)
---


Purpose

- Define inspection scope and gate expectations.

Scopes

- changed — current edits and nearby lines
- git — files changed since base (e.g., HEAD or origin/branch)
- full — project or modules

Workflow

- Loop: run `changed`, then `git` before commit.
- Gate: run `full` (or all touched modules) before merge.

Results Schema

- id, severity, file:line, message, fixable

Policy

- Zero‑warning on touched files before full gate; narrow suppressions only.
