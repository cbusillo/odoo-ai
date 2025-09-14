Title: Inspections (JetBrains)

Scopes

- changed — current edits and nearby lines
- git — files changed since base (e.g., HEAD or origin/branch)
- full — project or modules

Results Schema

- id, severity, file:line, message, fixable

Policy

- Zero‑warning on touched files before full gate; narrow suppressions only.

