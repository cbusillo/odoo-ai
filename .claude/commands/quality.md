---
description: Run comprehensive quality control checks using QC agent coordination
argument-hint: "[module_name|file_path] [--quick]"
---

@docs/agents/qc.md

Run comprehensive quality control checks coordinating multiple specialist agents.

Target: $ARGUMENTS (default: changed files)

QC agent coordinates quality checks across multiple dimensions:

**Comprehensive Review (default):**

- Inspector: Code quality, imports, patterns
- Flash: Performance bottlenecks, N+1 queries
- Scout: Test coverage and quality
- Security: Access controls, SQL injection

**Quick Review (--quick flag):**

- Inspector only: Code style, imports, basic patterns

**Use Cases:**

- Pre-commit: `quality changed --quick`
- Pre-push: `quality module_name`
- Full audit: `quality all`

QC provides consolidated reports and coordinates fixes through appropriate agents.