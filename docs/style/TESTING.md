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