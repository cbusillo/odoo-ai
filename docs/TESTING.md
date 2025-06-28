# Testing Guide

## Overview

This project uses Odoo 18's testing framework with three test layers:

- **Python Unit Tests** - Backend logic testing using `TransactionCase`
- **JavaScript Tests** - Frontend testing using Odoo's Hoot framework
- **Tour Tests** - End-to-end workflow testing

### Test File Naming Conventions

- **JavaScript unit tests**: `feature_name.test.js` in `static/tests/`
    - Example: `shipping_analytics.test.js`, `motor_form.test.js`
    - Template: Use `basic.test.js` as reference
- **Tour tests**: `feature_name_tour.js` in `static/tests/tours/`
    - Example: `motor_workflow_tour.js`, `basic_tour.js`
    - Template: Use `basic_tour.js` as reference
- **Python tests**: `test_feature_name.py` in `tests/`
    - Example: `test_order_importer.py`
    - Template: Use `test_template.py` as reference

## Running Tests

### Quick Start

```bash
# Enhanced test runner - uses docker CLI (no external Python dependencies)
python tools/test_runner.py           # Summary of test results (default)
./tools/test_runner.py all       # Run all tests
./tools/test_runner.py python    # Python tests only
./tools/test_runner.py js        # JavaScript tests only
./tools/test_runner.py tour      # Tour tests only
./tools/test_runner.py failing   # List currently failing tests

# Advanced options
./tools/test_runner.py -v                          # Verbose output with error details
./tools/test_runner.py --test-tags TestOrderImporter  # Run specific test class
./tools/test_runner.py --test-tags TestOrderImporter.test_import_order  # Run specific test method
./tools/test_runner.py -j                          # JSON output
./tools/test_runner.py -u all                      # Update module before tests
./tools/test_runner.py -t 300 all                  # Custom timeout (5 minutes)

```

### Test Tags

Tests in Odoo require proper tagging for discovery:

- **`post_install`** - Python unit tests (run after all modules installed)
- **`product_connect_js`** - JavaScript tests
- **`product_connect_tour`** - Tour/workflow tests

### Test Commands

All tests run through Docker using `odoo-bin`:

```bash
# Run all product_connect tests (use --log-level=info for debugging)
docker compose run --rm web /odoo/odoo-bin \
    --log-level=warn \
    --stop-after-init \
    --test-tags=product_connect \
    --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Run specific test class
docker compose run --rm web /odoo/odoo-bin \
    --test-tags=product_connect:TestMotor \
    --stop-after-init \
    --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Run specific test method
docker compose run --rm web /odoo/odoo-bin \
    --test-tags=product_connect:TestMotor.test_generate_qr_code \
    --stop-after-init \
    --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise
```

## Test Structure

```
addons/product_connect/
├── tests/                          # Python tests
│   ├── __init__.py                # Imports all tests
│   ├── test_motor.py              # Motor model tests
│   ├── test_product_template.py   # Product template tests
│   └── test_integration.py        # JS/Tour test runners
├── services/tests/                 # Service layer tests
│   ├── test_shopify_helpers.py    # Helper function tests
│   ├── test_product_exporter.py   # Export functionality tests
│   ├── test_shopify_sync.py       # Sync logic tests
│   ├── test_product_deleter.py    # Deletion logic tests
│   └── test_shopify_service.py    # API service tests
└── static/tests/                   # Frontend tests
    ├── *.test.js                  # Hoot JavaScript tests
    └── tours/*.js                 # Tour workflow tests
```

## Writing Tests

### JavaScript Unit Tests (Hoot Framework)

JavaScript tests use Odoo 18's Hoot testing framework. Create test files in `static/tests/`:

```javascript
// Template: basic.test.js
import { describe, test, expect } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { mountView } from "@web/../tests/web_test_helpers";

describe("Feature Name Tests", () => {
    test("should do something", async () => {
        const serverData = {
            models: {
                "model.name": {
                    fields: {
                        name: { string: "Name", type: "char" },
                    },
                    records: [
                        { id: 1, name: "Test" },
                    ],
                },
            },
        };

        const view = await mountView({
            type: "list",
            resModel: "model.name",
            serverData,
            arch: `<tree><field name="name"/></tree>`,
        });

        await animationFrame();
        expect(".o_data_row").toHaveCount(1);
    });
});
```

### Tour Tests

Tour tests simulate user interactions. Create in `static/tests/tours/`:

```javascript
// Template: basic_tour.js
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("feature_tour", {
    test: true,  // Important: marks this as a test tour
    steps: () => [
        {
            content: "Wait for page load",
            trigger: "body.o_web_client",
        },
        {
            content: "Click something",
            trigger: ".selector",
            run: "click",
        },
        // More steps...
    ],
});
```

**Important Notes**:

- Use `test: true` property for test tours (not for production tours)
- No `@odoo-module` directive needed for test files
- Tours must have unique names across the entire Odoo instance

### Mocking Best Practices

When mocking in tests, prefer `patch.object` over string-based patches for better refactoring support:

```python
from unittest.mock import patch, MagicMock

# PREFERRED: patch.object - type-safe and refactor-friendly
from ..shopify.sync.importers.customer_importer import CustomerImporter


class TestExample(TransactionCase):
    @patch.object(CustomerImporter, "import_customer")
    def test_with_mock(self, mock_import_customer: MagicMock) -> None:
        mock_import_customer.return_value = True
        # Your test code

# AVOID: String-based patches (unless patching import locations)
# @patch("odoo.addons.product_connect.services.shopify.sync.importers.customer_importer.CustomerImporter.import_customer")
```

**Exception**: When patching import locations (where a module imports another), string patches may be necessary:

```python
# OK for import location patching
self.shopify_service_patcher = patch("odoo.addons.product_connect.services.shopify.sync.base.ShopifyService")
```

### Base Test Classes

Use the provided base classes for consistent test setup:

```python
from odoo.addons.product_connect.tests.test_base import (
    ProductConnectTransactionCase,
    ProductConnectHttpCase,
    ProductConnectIntegrationCase
)


# For unit tests
class TestExample(ProductConnectTransactionCase):
    @classmethod
    def _setup_test_data(cls):
        # Override to add test-specific data
        pass


# For HTTP/browser tests needing authentication
class TestBrowser(ProductConnectHttpCase):
    def test_feature(self):
        # test_user and test_user_password are automatically created
        self.browser_js(url, code, login=self.test_user.login)


# For integration tests with motor data
class TestIntegration(ProductConnectIntegrationCase):
    def test_workflow(self):
        # test_user, test_user_password, and test_motor are available
        pass
```

### Python Tests

```python
from odoo.tests import TransactionCase


class TestExample(TransactionCase):
    def setUp(self) -> None:
        super().setUp()
        # Setup test data

    def test_something(self) -> None:
        # Test implementation
        self.assertEqual(actual, expected)
```

### HttpCase Tests (Browser/Tour Tests)

For tests requiring authentication (JavaScript tests, tours), create temporary test users:

```python
import secrets
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWithAuth(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create temporary test user with secure password (rolled back after tests)
        secure_password = secrets.token_urlsafe(32)
        cls.test_user = cls.env['res.users'].create({
            'name': 'Test User',
            'login': 'test_user_unique',
            'password': secure_password,
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        # Store password if needed for authentication
        cls.test_user_password = secure_password

    def test_browser_feature(self):
        self.browser_js(url, code, login=cls.test_user.login)
```

**Important**: Always use cryptographically secure passwords via `secrets.token_urlsafe()`. Test users are automatically
rolled back.

### JavaScript Tests (Hoot)

```javascript
import { describe, test, expect } from "@odoo/hoot";
import { click, fill } from "@odoo/hoot-dom";

describe("Feature Tests", () => {
    test("should do something", async () => {
        // Test implementation
        expect(value).toBe(expected);
    });
});
```

### Tour Tests

```javascript
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("tour_name", {
    steps: () => [
        {
            content: "Step description",
            trigger: "CSS selector",
            run: "click", // or "text value"
        },
    ],
});
```

## Test Tags

Tests are organized using tags:

- `product_connect` - All Python tests in the module
- `product_connect_js` - JavaScript integration tests
- `product_connect_tour` - Tour workflow tests

## Important Notes

1. **Always use `--stop-after-init`** for Python tests to prevent server hanging
2. **Avoid manual commits** in tests - Odoo manages transactions
3. **Mock external services** like Shopify API calls
4. **Tests auto-discovery** - New tests are picked up automatically
5. **Use descriptive names** following the pattern `test_<feature>_<scenario>`

## Testing Against Production Database

Our tests run against a copy of the production database (`opw`) rather than a clean test database. This approach:

**Benefits:**

- Catches real-world edge cases with existing data
- Tests integration with actual business data patterns
- Validates that changes work with current state

**Challenges:**

- Tests must handle existing data (e.g., delivery mappings already loaded from `data.xml`)
- Constraint violations possible when creating test data that already exists
- Tests may need to check for existing records before creating

**Best Practices:**

- Check for existing records before creating test data
- Use unique identifiers where possible
- Make tests defensive against existing data state
- Consider test order dependencies when data is shared

## Code Quality Testing

### JetBrains Inspection API

Use the inspection API for comprehensive code quality checks:

- `inspection_pycharm__trigger()` - Trigger full project inspection
- `inspection_pycharm__get_problems()` - Get detailed problems list
- `inspection_pycharm__get_categories()` - Get summary by category

**Integration with CI/CD**:

- Run before test execution to catch code quality issues
- Useful for detecting issues across the entire codebase

## Handling Test Failures

### Deprecated or Obsolete Tests

When tests fail, consider whether they might be testing deprecated functionality:

- **Features removed**: Test may be checking functionality that no longer exists
- **API changes**: Test may use old method signatures or field names
- **Business logic changes**: Test assumptions may no longer be valid
- **Threading detection**: Tests for threading-based test detection when we now use `env.registry.in_test_mode()`

**Best practice**: When fixing failing tests, first verify if the functionality being tested still exists and is
relevant. Remove tests for deprecated features rather than trying to fix them.

## Debugging Tests

- Use `--log-level=info` instead of `--log-level=warn` for more verbose output
- Add `--screenshots=/tmp/odoo_tests` for failure screenshots
- Use `ipdb` for Python debugging: `import ipdb; ipdb.set_trace()`
- Check test output for specific error messages and stack traces