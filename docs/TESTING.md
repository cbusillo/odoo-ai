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

- **JavaScript tests**: `feature_name.test.js` in `static/tests/`
    - Example: `shipping_analytics.test.js`, `motor_form.test.js`
    - Uses Odoo 18's Hoot framework for both unit and integration tests
    - **Unit Test Template**: See [`basic.test.js`](../addons/product_connect/static/tests/basic.test.js)

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

**Note**: We use `docker exec` with the existing `script-runner-1` container instead of `docker compose run` to avoid
creating temporary containers that clutter Docker.

```bash
# Run all product_connect tests (use --log-level=info for debugging)
docker exec odoo-opw-script-runner-1 /odoo/odoo-bin \
    --log-level=warn \
    --stop-after-init \
    --test-tags=product_connect \
    --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Run specific test class
docker exec odoo-opw-script-runner-1 /odoo/odoo-bin \
    --test-tags=product_connect:TestMotor \
    --stop-after-init \
    --addons-path=/volumes/addons,/odoo/addons,/volumes/enterprise

# Run specific test method
docker exec odoo-opw-script-runner-1 /odoo/odoo-bin \
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

## Writing Tests

**For comprehensive test writing patterns, templates, and best practices, see @docs/agents/scout.md**

Scout covers:

- Test templates and base classes
- SKU validation rules
- Mocking patterns
- Tour test creation
- Common test scenarios

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

### Base Test Classes

**See @docs/agents/scout.md for detailed base class usage and pre-created test data**

Quick reference:

- `ProductConnectTransactionCase` - Unit tests
- `ProductConnectHttpCase` - Browser/tour tests
- `ProductConnectIntegrationCase` - Motor integration tests

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

Odoo 18 uses the Hoot framework for JavaScript testing, supporting both unit and integration tests.

#### Unit Tests

```javascript
import { describe, test, expect } from "@odoo/hoot";

describe("Feature Tests", () => {
    test("should do something", async () => {
        // Test implementation
        expect(value).toBe(expected);
    });
});
```

#### Integration Tests

For testing views, widgets, and DOM interactions:

```javascript
import { describe, test, expect, beforeEach } from "@odoo/hoot";
import { click, fill } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { mountView } from "@web/../tests/web_test_helpers";

describe("Widget Integration Tests", () => {
    let serverData;

    beforeEach(() => {
        serverData = {
            models: {
                "test.model": {
                    fields: { name: { string: "Name", type: "char" } },
                    records: [{ id: 1, name: "Test" }],
                },
            },
        };
    });

    test("should interact with view", async () => {
        await mountView({
            type: "form",
            resModel: "test.model",
            resId: 1,
            serverData,
            arch: `<form><field name="name"/></form>`,
        });

        expect("input[name='name']").toHaveValue("Test");
        await fill("input[name='name']", "Updated");
        expect("input[name='name']").toHaveValue("Updated");
    });
});
```

### Tour Tests

```javascript
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("tour_name", {
    test: true,  // REQUIRED for test tours
    steps: () => [
        // Check for console errors during tour execution
        {
            trigger: "body",
            run: () => {
                const errors = window.odoo.__DEBUG__.services.notification.notifications.filter(n => n.type === "danger");
                if (errors.length) throw new Error(`Console errors: ${errors.map(e => e.message).join(", ")}`);
            },
        },
        {
            content: "Step description",
            trigger: "CSS selector",
            run: "click", // or "text value"
        },
    ],
});
```

### Tour Testing Best Practices

**See @docs/agents/scout.md for tour test patterns and limitations**

#### Current Limitations

- Tours execute quickly, can miss lazy-loaded components
- Asset bundles (`web.assets_backend_lazy`) load asynchronously
- Minimal error feedback - tours pass even with console errors
- Complex selectors break easily between Odoo versions

#### Comprehensive Tour Pattern

```javascript
registry.category("web_tour.tours").add("comprehensive_tour", {
    test: true,
    steps: () => [
        // 1. Initial error check
        {
            trigger: "body",
            run: () => {
                const errors = window.odoo.__DEBUG__.services.notification.notifications.filter(n => n.type === "danger");
                if (errors.length) throw new Error(`Initial errors: ${errors.map(e => e.message).join(", ")}`);
            },
        },
        // 2. Navigation with proper wait
        {
            content: "Navigate to app",
            trigger: ".o_app[data-menu-xmlid='product_connect.main_menu']",
            run: "click",
        },
        {
            content: "Wait for lazy assets to load",
            trigger: ".expected_lazy_element",
            timeout: 30000,  // Increase timeout for lazy loading
        },
        // 3. Functional interaction
        {
            content: "Test actual functionality",
            trigger: ".interactive_element",
            run: function() {
                // Verify initial state
                const initialState = this.el.dataset.state;
                if (initialState !== "expected") {
                    throw new Error(`Unexpected initial state: ${initialState}`);
                }
                
                // Perform action
                this.el.click();
            },
        },
        // 4. Verify results
        {
            content: "Verify action completed",
            trigger: ".result_element:contains('Success')",
            timeout: 10000,
        },
        // 5. Final error check
        {
            trigger: "body",
            run: () => {
                // Check for JS errors
                const errors = window.odoo.__DEBUG__.services.notification.notifications.filter(n => n.type === "danger");
                if (errors.length) throw new Error(`Errors during tour: ${errors.map(e => e.message).join(", ")}`);
                
                // Check console
                if (window.consoleErrors?.length) {
                    throw new Error(`Console errors: ${window.consoleErrors.join(", ")}`);
                }
            },
        },
    ],
});
```

#### Tour Testing Strategy

1. **Smoke Tests** (Current)
   - Verify UI loads without errors
   - Basic navigation works
   - Minimal functional testing

2. **Functional Tests** (Recommended)
   - Test actual user workflows
   - Verify data changes
   - Check view transitions
   - Monitor for errors throughout

3. **Comprehensive Tests** (Ideal)
   - Full workflow from start to finish
   - Multiple user personas
   - Edge cases and error handling
   - Performance monitoring

#### Common Tour Pitfalls

- **NO jQuery selectors**: Use native selectors only
- **NO :visible/:contains**: Use attribute selectors
- **Avoid timing races**: Use proper wait conditions
- **Check for errors**: Add error monitoring steps

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

## Code Quality

**See @docs/agents/inspector.md for comprehensive code quality workflows**

Quick check: Run `mcp__odoo-intelligence__pattern_analysis(pattern_type="all")`

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

**Tour fails with navigation/selector issues**

- In Odoo 18, use `/odoo` as the start URL (changed from `/web` in earlier versions)
- Use simple, stable selectors (avoid complex CSS selectors with `:visible`, `:not()`, etc.)
- Add `test: true` property to tour definition for test mode
- Use `.o_web_client` and `.o_action_manager` as reliable wait triggers
- Test runner classes should extend `ProductConnectHttpCase` which provides test user

**Lazy-loaded assets in tours**

- Multigraph and other custom views may be in `web.assets_backend_lazy`
- Add explicit timeouts to steps waiting for lazy components: `timeout: 30000`
- Use progressive selectors: wait for container before specific elements
- If tour fails on custom view, check if assets are loaded synchronously in production

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