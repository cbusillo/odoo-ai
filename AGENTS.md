# AGENTS.md

## Overview

Outboard Parts Warehouse runs a custom **Odoo 18 Enterprise** add‑on (`addons/product_connect`) that synchronizes
inventory, orders, and customers with **Shopify 2025‑04**.  
Codex should behave like an experienced Odoo core developer: favor explicit, type‑safe Python, follow Odoo ORM best
practice, and never add comments or docstrings to production code.

> **Workdir**  
> Start Codex in the monorepo root `odoo-opw/`. The add‑on lives in `addons/product_connect/`; switch into that
> directory when paths are relative to the add‑on.

---

### Environment setup (cloud sandbox)

```bash
apt-get update -qq
apt-get install -y libxml2-dev libxslt1-dev   # Odoo XML deps
pip install --upgrade pip
pip install -r requirements.txt
```

Set `dockerize=false` in scripts to skip Docker‑dependent steps when running in the cloud sandbox.

---

## How to explore & test

```bash
# open Odoo shell inside web container
docker compose exec web odoo shell

# run full test suite (both runtimes)
python -m pytest addons/product_connect/tests -q

# run linters & type‑checker
scripts/lint.sh          # wraps black & pylint
python -m mypy -p addons.product_connect
```

---

## Coding standards

1. **No inline comments or docstrings** – express intent with full‑word identifiers.
2. **Type hints everywhere**; avoid `Any` unless indispensable.
3. Avoid `attr`, `getattr` or dynamic attribute tricks – they break static analysis.
4. Use **Odoo 18** patterns only.
5. Descriptive names (`update_quantity`, not `upd_qty`).
6. PEP 8 compliance; formatted by *black* in check mode.
7. New functionality **must include unit tests** in `addons/product_connect/tests`.
8. Full type hints on functions.

---

## Project‑specific workflows

### Implementing a feature or bug‑fix

```
git checkout -b feat/<short‑slug> opw-testing
# if Shopify schema changed:
docker/scripts/generate_shopify_models.py
# write failing test first
python -m pytest addons/product_connect/tests -q
# implement feature
scripts/lint.sh && python -m pytest
git push --set-upstream origin HEAD
open PR against opw-testing
```

## Environment description

```yaml
language: python
python_version: "3.13"
frameworks:
  - odoo: "18.0"
  - graphql: ariadne-codegen
services:
  - postgres: "17"
  - docker
linters:
  - mypy
  - pylint
  - black (check)
tests:
  runner: pytest
  command: python -m pytest addons/product_connect/tests -q
```

---

## Forbidden patterns

| Anti‑pattern                                         | Why it is disallowed                    |
|------------------------------------------------------|-----------------------------------------|
| `attr.*`, `getattr()` for field access               | Breaks static analysis & IDE completion |
| Comments / docstrings in production code             | Violates project style                  |
| Direct SQL without ORM or savepoints                 | Dangerous in Odoo                       |
| Writing to Odoo models inside loops without batching | Causes commit thrashing                 |

---

## Agent checklist before submitting work

- [ ] Code compiles (`python -m py_compile`).
- [ ] `mypy --strict` passes.
- [ ] `scripts/lint.sh` has zero findings.
- [ ] All unit tests pass.
- [ ] No new TODO/FIXME markers.
- [ ] No dynamic `attr` access introduced.
- [ ] All commits reference an open Jira ticket.
- [ ] New models/fields have matching security rules & views.

---

## Common commands

```bash
# Run only Shopify sync tests
python -m pytest addons/product_connect/tests/test_shopify_sync.py -q

# Recreate dev database with demo data
docker compose exec web odoo-bin -d opw --i18n-load=en_US --init base,product_connect --stop-after-init
```

---

## References

* OpenAI Codex launch blog post – 2025‑05‑16
* Codex CLI user guide
* Odoo 18 ORM reference
* Shopify Admin GraphQL 2025‑04 docs  

