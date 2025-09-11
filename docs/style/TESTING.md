# Testing Style Rules

Test-specific patterns and validation rules.

## SKU Validation Rules

**Consumable products require 4-8 digit SKUs**: Products with `type='consu'` must have numeric SKUs

- **Valid examples**: "1234", "12345678", "00001234"
- **Invalid examples**: "ABC123", "TEST-001", "12", "123456789"
- **Service products exempt**: Products with `type='service'` can have any SKU format
- **Bypass validation**: Use `with_context(skip_sku_check=True)` when needed

## Test Class Inheritance

**Always use base test classes** to avoid SKU validation errors:

```python
from odoo.addons.product_connect.tests.fixtures.test_base import (
    ProductConnectTransactionCase,  # For unit tests
    ProductConnectHttpCase,  # For browser/auth tests  
    ProductConnectIntegrationCase  # For motor integration
)
```

**Pre-created test data** (don't create duplicates!):

- `self.test_product` - Standard consumable (SKU: 10000001)
- `self.test_service` - Service product (SKU: SERVICE-001)
- `self.test_product_ready` - Ready-for-sale product
- `self.test_products` - List of 10 products
- `self.test_partner` - Test customer
- `self.test_user` - Test user (HttpCase only)

## Test Tags (REQUIRED)

```python
@tagged("post_install", "-at_install")  # Python tests
@tagged("post_install", "-at_install", "product_connect_tour")  # Tour runners
```

## File Naming Patterns

```
tests/
├── test_model_*.py       # Model tests (e.g., test_model_motor.py)
├── test_service_*.py     # Service tests (e.g., test_service_shopify.py)
├── test_tour_*.py        # Tour runners (e.g., test_tour_workflow.py)
└── test_*.py             # Other tests

static/tests/
├── *.test.js            # JavaScript unit tests
└── tours/*.js           # Tour definitions
```

## Mocking Best Practices

```python
from unittest.mock import patch, MagicMock

# PREFERRED: patch.object
from ..services.shopify.client import ShopifyClient


@patch.object(ShopifyClient, "execute")
def test_with_mock(self, mock_execute: MagicMock):
    mock_execute.return_value = {"data": {...}}
```

## Tour Test Patterns

**JavaScript Tour Tests:**

```javascript
// static/tests/tours/feature_tour.js
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("feature_tour", {
    test: true,  // REQUIRED!
    url: "/odoo",  // Odoo 18 uses /odoo, not /web
    steps: () => [
        {
            trigger: ".o_app[data-menu-xmlid='module.menu_id']",
            content: "Open app",
            run: "click",
        },
        // Simple selectors only - no :visible or :contains()
    ],
});
```

**Python Tour Runner:**

```python
@tagged("post_install", "-at_install", "product_connect_tour")
class TestFeatureTour(ProductConnectHttpCase):
    def test_feature_tour(self):
        self.start_tour("/odoo", "feature_tour", login=self.test_user.login)
```

## Common Test Patterns

### Testing Model Methods

```python
def test_compute_method(self):
    # Trigger compute
    self.test_product.invalidate_recordset(['computed_field'])
    # Force recomputation
    self.assertEqual(self.test_product.computed_field, expected_value)
```

### Testing Constraints

```python
def test_constraint_violation(self):
    with self.assertRaisesRegex(ValidationError, "Expected message"):
        self.test_product.write({'invalid_field': 'bad_value'})
```

## What NOT to Do

- ❌ Create products with invalid SKUs (use base classes!)
- ❌ Forget test tags (tests won't run!)
- ❌ Use jQuery patterns in tours (`:visible`, `:contains`)
- ❌ Create test users without secure passwords
- ❌ Commit in tests (Odoo handles transactions)

## Runner & Logs

Use our Docker‑aware runner to execute tests and collect structured artifacts.

- Phases: Unit → JS → Integration → Tour (in that order)
- Commands:
    - `uv run test-all` — run all phases and aggregate results
    - `uv run test-unit` | `uv run test-js` | `uv run test-integration` | `uv run test-tour`
    - `uv run test-clean` — drop test DBs and filestores
    - `uv run test-gate [--json]` — one-call: ensure running, wait, print bottom line, exit 0/1
    - Advanced:
        - `uv run test-launch` — start in background (JSON pid)
        - `uv run test-wait [--wait --timeout 7200 --json]` — poll/await completion
        - `uv run test-bottomline [--json]` — bottom-line summary only
- Timeouts: configured in `pyproject.toml` under `[tool.odoo-test.timeouts]`
- Logs: `tmp/test-logs/test-YYYYMMDD_HHMMSS/` with per‑phase `all.log`, `all.summary.json`, `all.failures.json` and a
  session `summary.json`/`digest.json` at the root.
    - `tmp/test-logs/current` → the in‑progress session (set when a run starts; cleared when it finishes)
    - `tmp/test-logs/latest`  → the most recent completed session
- DB strategy: unit split uses `opw_ut_<module>`; clone‑based phases use `opw_test_<phase>`. Cleanup removes both
  patterns.
- Tips: If your shell sandbox blocks Docker, use the PyCharm “All Tests” run config. For JS/Tour timeouts, warm the
  instance or raise the phase timeout in `pyproject.toml`.

## LLM‑Friendly Results (Do Not Tail/Head)

- The runner writes structured JSON you can parse instead of scraping terminal output.
- Preferred checks (in order):
    - During a run: `tmp/test-logs/current/summary.json` (if present), otherwise
    - After completion: `tmp/test-logs/latest/summary.json` → overall session summary (`success: true|false`).
    - Per‑phase aggregate: `tmp/test-logs/<session>/<phase>/all.summary.json` (e.g., `unit/all.summary.json`).
    - Counts:
        - By default, JS counts use definitions (number of `test(...)` in `*.test.js`). Python counts come from Odoo
          logs.
        - To use executed Hoot totals instead, set `JS_COUNT_STRATEGY=runtime`.

Tips

- `uv run test-wait` prefers `current` when present, then falls back to `latest`. Use `--session` to target a specific
  run.
    - Simplest agent path: `uv run test-gate --json` (single call; exits 0/1).
- Minimal Python snippet to assert pass/fail:
  ```bash
  python - <<'PY'
  import json, pathlib, sys
  latest = pathlib.Path('tmp/test-logs/latest')
  with open(latest/'summary.json') as f:
      s = json.load(f)
  ok = bool(s.get('success'))
  print('tests_success:', ok)
  sys.exit(0 if ok else 1)
  PY
  ```
- Never rely on `| tail` / `| head` / `timeout ... | tail` to infer success; these can truncate summaries and mislead
  agents. Always read the JSON files.
