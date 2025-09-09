# Subagent Workflow (Claude Code)

Goal: Keep the main Claude context clean for planning and arbitration by delegating focused work to subagents with minimal context, scoped tools, and deliberate model choices.

Why subagents
- Context isolation: Each subagent has its own window, preventing context bloat in the main thread.
- Tool focus: Grant only the tools a subagent needs; reduce risk and cognitive load.
- Cost/latency control: Route easy tasks to lighter models; reserve heavier models for hard reasoning.

When to delegate (thresholds)
- 5+ files or bulk operations (rename, refactor, format, codemods)
- Broad research/pattern finding (codebase scans, framework spelunking)
- Test scaffolding and fixtures; browser tour authoring
- Long‑running or multi‑stage tasks (research → implement → verify)

Subagent contract (do the work, then report)
- Apply changes: make the minimal edits/files needed (don’t wait for manual apply unless the change is risky/large)
- Test: run `uv run test-unit addons/<module>` (or targeted tests) and iterate until green
- Evidence: cite file paths and key lines; save long logs/artifacts to `tmp/subagent-runs/<RUN_ID>/<agent>/`
- Summary: Decision • Diffs/Paths • Test results • Next steps • Risks/assumptions

Acceptance gate
- Do not finish until the targeted tests pass, or you’ve applied fixes and provided a concise failure summary with next actions.

Tool scope and safety
- Grant only needed MCP tools (e.g., odoo‑intelligence, docker, playwright) per subagent.
- Use read‑only modes by default; enable write only for implementation steps with human approval.
- Keep container‑only paths behind Odoo/Docker tools; never read `/odoo/*` from host.

Model routing (Claude‑specific)
- Research, grep‑like scans, linting → lighter model (e.g., Haiku)
- Standard development and test scaffolding → balanced model (e.g., Sonnet)
- Deep analysis and migrations → heavier model (e.g., Opus)

Notes
- Model names and availability change. Select per subagent using Claude Code’s model selector; keep a lightweight default and escalate only when acceptance criteria require it.

Prompt skeleton (system/user)
- System: “You are the {role}. Do only {scope}. Use only these tools: {tools}. Apply changes and run tests. Return the Subagent Contract.”
- User: “Task. Acceptance criteria. Artifacts directory. Time budget. When uncertain, state risks and stop.”

Artifacts
- Save outputs under `tmp/subagent-runs/{YYYYMMDD_HHMM}/{subagent_name}/` (notes, search JSON, diffs, logs).

Parallelization
- For independent steps (e.g., multi‑pattern searches), prefer parallel tool calls; aggregate a single concise report per contract above.

Delegation examples
- Research patterns → Archer subagent (search tools); lighter model; no edits.
- Scaffold and run tests → Scout subagent (write tests into addon, run `uv run test-unit addons/<module>`, iterate).
- Implement feature → Odoo Engineer subagent (edit files; small, focused commits; run tests each pass).
- Inspect/fix → Inspector subagent (low‑risk fixes; rerun tests; summarize issues and applied fixes).

Extra addons as submodules (operator rule of thumb)
- When adding external addons, initialize them as submodules:
  - `git submodule add <repo-url> addons/<addon_name>`
  - Commit `.gitmodules` and the submodule entry
  - Ensure compose mounts already include `./addons` → `/volumes/addons` (no extra mapping needed)
- For integration work on submodules, prefer PRs against the submodule repo rather than committing generated files inside this repo.
