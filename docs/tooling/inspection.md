---
title: Inspections (JetBrains)
---


Purpose

- Define inspection scope and zero-warning expectations.

When

- During development loops and before merge.

When not to use

- Never skip inspections for touched files.

Scope and order

1. Loop: `changed`, then `git` before commit.
2. Gate: `full` (or all touched modules) before merge.

Scopes

- changed — current edits and nearby lines.
- git — files changed since base (e.g., HEAD or origin/branch).
- full — project or modules.
