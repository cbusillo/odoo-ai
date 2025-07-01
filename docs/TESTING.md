# Testing Guide

## Overview

This project uses Odoo 18's testing framework with three test layers:

- **Python Unit Tests** - Backend logic testing using `TransactionCase`
- **JavaScript Tests** - Frontend testing using Odoo's Hoot framework
- **Tour Tests** - End-to-end workflow testing

### Test File Structure

**Important**: Odoo's test discovery only works with files directly in the `tests/` directory. Tests in subdirectories
are not automatically discovered.

#### Directory Structure

```
tests/
├── fixtures/              # Test helpers and base classes
│   ├── test_base.py      # Base test classes (TransactionCase, HttpCase, etc.)
│   ├── test_service_base.py
│   └── shopify_responses.py
├── test_model_*.py       # Model tests (e.g., test_model_motor.py)
├── test_service_*.py     # Service tests (e.g., test_service_order_importer.py)
├── test_tour_*.py        # Tour runners (e.g., test_tour_motor_workflow.py)
└── test_*.py             # Other tests
```

#### Naming Conventions

- **Python tests**: Use prefixes to indicate test type
    - `test_model_*.py` - Model and business logic tests
    - `test_service_*.py` - Service layer tests (API clients, importers, etc.)
    - `test_tour_*.py` - Tour test runners
    - Example: `test_model_motor.py`, `test_service_order_importer.py`, `test_tour_shipping_analytics.py`
    - **Template**: See [`test_basic.py`](../addons/product_connect/tests/test_basic.py)

- **JavaScript unit tests**: `feature_name.test.js` in `static/tests/`
    - Example: `shipping_analytics.test.js`, `motor_form.test.js`
    - **Template**: See [`basic.test.js`](../addons/product_connect/static/tests/basic.test.js)

- **Tour definitions**: `feature_name_tour.js` in `static/tests/tours/`
    - Example: `motor_workflow_to_enabled_product_tour.js`, `basic_tour.js`
    - **Template**: See [`basic_tour.js`](../addons/product_connect/static/tests/tours/basic_tour.js)

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
│   ├── test_*.py                  # Feature unit tests
│   ├── test_tour_coverage.py      # Ensures all tours have runners
│   └── tours/                     # Tour test runners
│       ├── __init__.py
│       └── test_*_tour.py         # Tour runners for UI tests
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

### Test Templates

Use these templates as starting points for new tests:

- **Python unit test**: [`test_basic.py`](../addons/product_connect/tests/test_basic.py)
    - Shows TransactionCase and HttpCase examples
    - Demonstrates mocking with patch.object
    - Includes secure password generation for test users

- **JavaScript test**: [`basic.test.js`](../addons/product_connect/static/tests/basic.test.js)
    - Hoot framework example
    - Shows view mounting and DOM testing

- **Tour test**: [`basic_tour.js`](../addons/product_connect/static/tests/tours/basic_tour.js)
    - Minimal tour structure
    - Shows basic UI verification

### Tour Tests

Tour tests simulate user interactions. Create in `static/tests/tours/`:

**Important**: All test classes MUST have the `@tagged` decorator to be discovered by Odoo's test runner. Tests without
this decorator will not run!

**Updated Pattern**: Keep unit tests and tour runners in separate files for better organization:

```python
# tests/test_model_feature.py - Model/business logic tests
@tagged("post_install", "-at_install")  # REQUIRED!
class TestFeatureName(ProductConnectTransactionCase):
    """Unit tests for the feature"""

    def test_business_logic(self):
        # Test models, computations, etc.
        pass


# tests/test_tour_feature.py - Tour runner
@tagged("post_install", "-at_install", "product_connect_tour")  # REQUIRED!
class TestFeatureNameTour(ProductConnectHttpCase):
    """Tour runner for UI tests"""

    def test_feature_name_tour(self):
        self.start_tour("/odoo", "feature_name_tour", login=self.test_user.login)
```

This pattern provides:

- **Feature cohesion**: All tests for a feature in one file
- **Better debugging**: Tour failures have context about what feature broke
- **Clear ownership**: Developers know where to add tests

**Tour Organization**:

Tours follow a clear pattern to ensure proper execution:

1. **Tour definitions**: `static/tests/tours/feature_name_tour.js` - UI interaction scripts
2. **Tour runners**: `tests/test_tour_feature_name.py` - Python test classes that execute tours
3. **Naming**: Tour runners use prefix `test_tour_` for easy identification

This structure ensures:

- All tours have corresponding runners (no silent passes)
- Clear separation between tour logic and test execution
- Easy identification of test types by prefix

**Running Tours**:

1. **Via test_runner.py** (recommended for CI/CD):
   ```bash
   ./tools/test_runner.py tour                    # Run all tours
   ./tools/test_runner.py tour --test-tags TestMotorWorkflow  # Specific test class
   ```

2. **Via browser console** (for debugging):
   ```javascript
   // List all loaded tours
   Object.keys(odoo.__WOWL_DEBUG__.root.env.services.tour.tours)
   
   // Run a specific tour
   odoo.__WOWL_DEBUG__.root.env.services.tour.run("motor_workflow_tour")
   ```

**Important Notes**:

- Tours are automatically available in test mode (no special property needed)
- No `@odoo-module` directive needed for test files
- Tours must have unique names across the entire Odoo instance
- **Database changes**: In tests, changes are rolled back. In browser, changes are permanent!
- Tours in `static/tests/tours/` are for testing only (won't appear in Tours UI)
- To make tours visible in Tours UI, move to `static/src/tours/` and update manifest

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

### Common Tour Test Issues

**OwlError: Failed to evaluate domain**

- Use Odoo domain functions: `context_today()`, `relativedelta()`
- Avoid Python datetime expressions: `datetime.datetime.now()`
- Example fix: `domain="[('date', '>=', context_today().strftime('%Y-%m-%d'))]"`

**Tour not executing in test runner**

- Check the feature test file has a tour runner class with `product_connect_tour` tag
- Verify tour registration syntax: `registry.category("web_tour.tours").add("tour_name"`
- Ensure module update was run after adding tour file

**Tour data conflicts**

- Create unique test data (use timestamps: `Date.now()`)
- Tours run against production database copy - handle existing data
- Clean up test data at tour end

**Test Environment vs Browser Console**

Tours behave differently in test mode vs browser console:

**Test Mode** (`./tools/test_runner.py tour`):

- Database changes are rolled back
- Runs with test user authentication
- Timeout enforced (120 seconds default)
- Failures tracked in test results

**Browser Console** (`odoo.__WOWL_DEBUG__.root.env.services.tour.run("tour_name")`):

- Database changes are permanent
- Runs with current user session
- No timeout
- Manual debugging possible with DevTools