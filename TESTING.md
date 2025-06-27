# Testing Guide

## Overview

This project uses Odoo 18's testing framework with three test layers:

- **Python Unit Tests** - Backend logic testing using `TransactionCase`
- **JavaScript Tests** - Frontend testing using Odoo's Hoot framework
- **Tour Tests** - End-to-end workflow testing

## Running Tests

### Quick Start

```bash
# Enhanced Python test runner - optimized for CI/CD and Claude Code
python tools/test_runner.py           # Summary of test results (default)
python tools/test_runner.py all       # Run all tests
python tools/test_runner.py python    # Python tests only
python tools/test_runner.py js        # JavaScript tests only
python tools/test_runner.py tour      # Tour tests only
python tools/test_runner.py failing   # List currently failing tests

# Advanced options
python tools/test_runner.py -v                          # Verbose output with error details
python tools/test_runner.py --test-tags TestOrderImporter  # Run specific test class
python tools/test_runner.py -j                          # JSON output
python tools/test_runner.py -u all                      # Update module before tests
python tools/test_runner.py -t 300 all                  # Custom timeout (5 minutes)

```

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

## Debugging Tests

- Use `--log-level=info` instead of `--log-level=warn` for more verbose output
- Add `--screenshots=/tmp/odoo_tests` for failure screenshots
- Use `ipdb` for Python debugging: `import ipdb; ipdb.set_trace()`
- Check test output for specific error messages and stack traces