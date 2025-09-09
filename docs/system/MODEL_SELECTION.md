# Model Selection Guide (Provider‑Agnostic)

## Overview

Keep guidance resilient to provider changes. Avoid hardcoding vendor model names and numeric claims.

## Principles

- Use the tool’s configured default model unless a task explicitly needs a different one.
- Choose a large‑context model only when the input truly requires it.
- Prefer profiles to encode recurring choices (e.g., “quick”, “dev‑standard”, “deep‑reasoning”, “test‑runner”).

## Environment knobs

- `OPENAI_PRIMARY_MODEL` — Optional override for the default model.
- `OPENAI_LARGE_CONTEXT_MODEL` — Optional; set only if a large‑context model is available and necessary.

## Routing tips

- Quick lookups and small edits → lightweight/default profile
- Standard implementation and refactors → dev‑standard
- Complex analysis and big refactors → deep‑reasoning
- Test execution and debugging loops → test‑runner

## Notes

- If you hit context limits, split the work or select a large‑context profile configured for your account.
- Don’t include vendor‑specific latency, token sizes, or success‑rate tables in docs; these drift and vary by account.
- Keep model choices centralized in config or profiles; avoid scattering per‑doc defaults.
