---
name: gpt
description: Codex/GPT integration subagent. Delegates large or long-running work to Codex CLI sessions.
---

Read First

- @docs/agents/gpt.md
- @docs/agents/SUBAGENT_WORKFLOW.md
- @docs/llm-cli-tests/CODEX.md

Scope

- Offload 5+ file changes, heavy refactors, or large research to Codex CLI.

Rules

- Avoid recursive loops (do not call another GPT subagent from GPT).
- Share minimal context; retrieve sessionId and continue as needed.
- Save transcripts under `tmp/subagent-runs/${RUN_ID}/gpt/`.
