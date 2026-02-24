---
title: Gate Benchmark
---

Purpose

- Compare local gate runtime against GitHub workflow runtime using measured
  p50/p95 data.

When

- Before deciding whether testing/prod gate authority should run on
  GitHub-hosted or self-hosted runners.

Sources of Truth

- `tools/gate_benchmark.py`
- `.github/workflows/test-gate.yml`
- GitHub Actions workflow run history (`gh api repos/<owner>/<repo>/actions/...`)

Usage

```bash
# Full comparison (local + GitHub)
uv run gate-benchmark \
  --stack cm \
  --branch cm-testing \
  --workflow test-gate.yml \
  --local-samples 1 \
  --github-samples 10 \
  --json-output

# GitHub-only comparison using historical runs
uv run gate-benchmark \
  --stack cm \
  --branch cm-testing \
  --workflow test-gate.yml \
  --skip-local \
  --github-samples 20 \
  --json-output

# Local-only measurement (useful while workflow is being prepared)
uv run gate-benchmark \
  --stack cm \
  --branch cm-testing \
  --workflow test-gate.yml \
  --skip-github \
  --local-samples 2 \
  --json-output
```

Workflow trigger examples

```bash
# GitHub-hosted benchmark run
gh workflow run test-gate.yml \
  --ref cm-testing \
  -f stack=cm \
  -f runner_label=ubuntu-latest

# Self-hosted benchmark run (replace label with your runner label)
gh workflow run test-gate.yml \
  --ref cm-testing \
  -f stack=cm \
  -f runner_label=self-hosted
```

Notes

- Local benchmark command is `uv run test run --json --stack <stack>`.
- GitHub benchmark uses completed workflow runs for the selected branch and
  workflow.
- If workflow history is missing, the command reports an explicit error in the
  GitHub section while still returning local results.
