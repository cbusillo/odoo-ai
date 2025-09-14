# Testing

Use the unified test CLI via `uv run`. Keep inner loops fast and run the full gate at the end.

Pointers

- Style/patterns: [style/testing.md](style/testing.md)
- Advanced testing: [style/testing-advanced.md](style/testing-advanced.md)
- Workflow: [workflows/testing-workflow.md](workflows/testing-workflow.md)

Commands (recommended)

```bash
uv run test unit                   # Fast unit tests
uv run test js                     # JS/hoot tests
uv run test integration            # Integration tests
uv run test tour                   # Browser/UI tours
uv run test run --json             # Full gate (all phases)
uv run test plan --phase all       # Print sharding plan (JSON)
uv run test doctor                 # Environment diagnostics
```

Filters

- Use `--modules a,b` (and per‑phase equivalents) to scope runs during the loop.

Detached mode

- Add `--detached` for long runs; poll with `uv run test wait --json`.

Gate on JSON

- Read `tmp/test-logs/latest/summary.json` and require `success: true` before merging.
