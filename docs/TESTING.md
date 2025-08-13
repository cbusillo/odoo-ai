# Testing Guide

## Overview

This project uses a modern UV-based test infrastructure with Odoo 18's testing framework. The system provides three test
layers with clean separation and reliable execution.

**Test Statistics**: Run `uv run test-stats` for current counts  
**Total Runtime**: < 30 minutes for complete suite  
**Infrastructure**: Uses script-runner container to avoid circular imports

## Quick Start

### ⚠️ CRITICAL: Always Use `uv run` Commands

**NEVER run test scripts directly!** The test infrastructure requires `uv run`:

- ✅ **CORRECT**: `uv run test-unit`
- ❌ **WRONG**: `python tools/test_runner.py`
- ❌ **WRONG**: `.venv/bin/python tools/test_runner.py`
- ❌ **WRONG**: `/Users/.../odoo-opw/.venv/bin/python tools/test_runner.py`

### Simple Commands (Recommended)

```bash
# Core test commands (these just work!)
uv run test-unit          # Fast unit tests (< 2 min)
uv run test-integration   # Integration tests (< 10 min)  
uv run test-tour          # Browser UI tests (< 15 min)
uv run test-all           # Complete test suite (< 30 min)
uv run test-quick         # Quick verification tests
uv run test-stats         # Show test statistics

# Test utilities
uv run test-setup         # Initialize test databases
uv run test-clean         # Remove test artifacts  
uv run test-report        # Generate HTML report
# uv run test-watch       # TDD watch mode (not yet implemented)
```

**That's it!** These commands handle all the complexity internally.

### What Makes This Work

- **Script-runner container**: Avoids circular import issues
- **Automatic database management**: Fresh databases as needed
- **Test tags**: `unit_test`, `integration_test`, `tour_test`
- **Output streaming**: Real-time progress updates
- **Error handling**: Clean failures with actionable feedback

## Test Types

### Unit Tests (`unit_test` tag)

- **Purpose**: Fast, isolated business logic testing
- **Runtime**: < 2 minutes
- **Database**: Fresh database per run
- **Examples**: Model validation, computed fields, constraints

### Integration Tests (`integration_test` tag)

- **Purpose**: Service layer and API integration testing
- **Runtime**: < 10 minutes
- **Database**: Stable test database with snapshots
- **Examples**: Shopify sync, order import, external API calls

### Tour Tests (`tour_test` tag)

- **Purpose**: End-to-end browser workflow testing
- **Runtime**: < 15 minutes
- **Database**: Staging database with full demo data
- **Examples**: UI interactions, complete user workflows

## Advanced Usage

### Custom Test Selection (Not Yet Implemented)

```bash
# Planned capabilities (not yet implemented)
# uv run test-unit --pattern "test_motor*"
# uv run test-integration --tags "shopify"  
# uv run test-tour --exclude "slow"

# Debug modes (not yet implemented)
# uv run test-unit --verbose
# uv run test-all --debug
```

### Development Workflow

```bash
# 1. Quick feedback loop
uv run test-quick           # Fast smoke tests

# 2. Feature development  
uv run test-unit           # Verify business logic
uv run test-integration    # Check integrations

# 3. Before commit
uv run test-all            # Full validation
uv run test-report         # Generate HTML report
```

## Test Organization

### Directory Structure

```
addons/product_connect/tests/
├── fixtures/                # Test helpers and factories
│   ├── __init__.py
│   ├── base.py             # Base test classes  
│   ├── factories.py        # Data factories
│   └── shopify_responses.py # Mock responses
├── unit/                   # Pure unit tests
│   ├── __init__.py
│   └── test_*.py          # Fast, isolated tests
├── integration/            # Service/API tests
│   ├── __init__.py  
│   └── test_*.py          # Integration tests
└── tour/                   # Browser UI tests
    ├── __init__.py
    └── test_*.py          # Tour runners
```

### Test Tags (Critical for Discovery)

All tests MUST use proper tagging:

```python
from odoo.tests import tagged


# Unit tests
@tagged("unit_test", "post_install", "-at_install")
class TestProductLogic(UnitTestCase):
    pass


# Integration tests
@tagged("integration_test", "post_install", "-at_install")
class TestShopifySync(IntegrationTestCase):
    pass


# Tour tests
@tagged("tour_test", "post_install", "-at_install")
class TestUserWorkflow(TourTestCase):
    pass
```

## Base Test Classes

### UnitTestCase

```python
from ..fixtures import UnitTestCase, ProductFactory

@tagged("unit_test", "post_install", "-at_install")
class TestExample(UnitTestCase):
    def test_business_logic(self):
        product = ProductFactory.create(self.env)
        self.assertRecordValues(product, {"type": "consu"})
```

### IntegrationTestCase

```python
from ..fixtures import IntegrationTestCase


@tagged("integration_test", "post_install", "-at_install")
class TestShopifyAPI(IntegrationTestCase):
    def test_api_integration(self):
        # Mock external services
        with self.mock_shopify_client():
            result = self.service.sync_products()
            self.assertTrue(result.success)
```

### TourTestCase

```python
from ..fixtures import TourTestCase

@tagged("tour_test", "post_install", "-at_install") 
class TestUIWorkflow(TourTestCase):
    def test_product_creation(self):
        self.start_tour("/odoo", "product_creation_tour")
```

## JavaScript/Tour Testing

### Test File Structure

```
static/tests/
├── *.test.js              # Hoot unit/integration tests
└── tours/*.js             # Tour workflow definitions
```

### Hoot JavaScript Tests

```javascript
import { describe, test, expect } from "@odoo/hoot";
import { click, fill } from "@odoo/hoot-dom";
import { mountView } from "@web/../tests/web_test_helpers";

describe("Widget Tests", () => {
    test("should handle user input", async () => {
        await mountView({
            type: "form",
            resModel: "product.template",
            serverData: mockData,
            arch: `<form><field name="name"/></form>`,
        });

        expect("input[name='name']").toHaveValue("Test");
        await fill("input[name='name']", "Updated");
        expect("input[name='name']").toHaveValue("Updated");
    });
});
```

### Tour Definitions

```javascript
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("product_creation_tour", {
    test: true,  // REQUIRED for test tours
    steps: () => [
        {
            content: "Navigate to products",
            trigger: ".o_app[data-menu-xmlid='product_connect.main_menu']",
            run: "click",
        },
        {
            content: "Create new product", 
            trigger: ".o_list_button_add",
            run: "click",
        },
        {
            content: "Fill product name",
            trigger: "input[name='name']",
            run: "text Test Product",
        },
        {
            content: "Save product",
            trigger: ".o_form_button_save",
            run: "click",
        },
    ],
});
```

## Factory Pattern (Recommended)

Replace hardcoded test data with dynamic factories to avoid conflicts:

```python
# ❌ OLD - Causes conflicts
product = self.env["product.template"].create({
    "default_code": "TEST001",  # Will conflict with other tests!
})

# ✅ NEW - Unique every time  
from ..fixtures import ProductFactory
product = ProductFactory.create(self.env)
```

### Available Factories

- **ProductFactory** - Standard products with unique SKUs
- **PartnerFactory** - Customers/vendors with contacts
- **MotorFactory** - Motor-specific products
- **ShopifyProductFactory** - Products with Shopify metadata
- **SaleOrderFactory** - Orders with line items

### Factory Usage

```python
# Single record
product = ProductFactory.create(env, name="Custom Name")

# Multiple records
products = ProductFactory.create_batch(env, count=5)

# Complex scenarios
company, contacts = PartnerFactory.create_with_contacts(env)
product = ProductFactory.create_with_variants(env, variant_count=3)
```

## Best Practices

### Test Writing

1. **Use factories**: Avoid hardcoded test data
2. **Proper tagging**: Required for test discovery
3. **Clear assertions**: Use descriptive failure messages
4. **Mock externals**: Don't depend on external services
5. **Test isolation**: Each test should be independent

### Tour Testing

1. **Start URL**: Use `/odoo` for Odoo 18 (changed from `/web`)
2. **Stable selectors**: Avoid complex CSS selectors
3. **Wait conditions**: Use proper timeouts for async operations
4. **Error monitoring**: Check for JavaScript errors in tours
5. **Test data**: Use unique identifiers to avoid conflicts

### Performance

1. **Unit tests first**: Fast feedback for business logic
2. **Integration selectively**: Only test actual integrations
3. **Tours sparingly**: Focus on critical user workflows
4. **Parallel execution**: Enabled for faster runs (planned)

## Troubleshooting

### Tests Not Running

- Check test tags are properly applied
- Verify test files are in correct directories
- Ensure base classes are imported correctly
- Run `uv run test-stats` to see discovered tests

### Common Issues

#### Import Errors

```bash
# Solution: Use relative imports from fixtures
from ..fixtures import UnitTestCase, ProductFactory
```

#### Database Conflicts

```bash
# Solution: Clean up test databases
uv run test-clean
```

#### Tour Failures

```bash
# Check for JavaScript errors in tours
# Use stable selectors, avoid timing issues
# Increase timeouts for lazy-loaded components
```

### Getting Help

1. **Test statistics**: `uv run test-stats` shows test counts
2. **Verbose output**: Add `--verbose` flag for details
3. **HTML reports**: `uv run test-report` for detailed analysis
4. **Clean slate**: `uv run test-clean` removes all artifacts

## Migration Notes

This project has migrated from the old monolithic test runner to a modern UV-based system:

- **Before**: 1572-line test_runner.py with ~60% reliability
- **After**: Clean, modular system with 95%+ reliability
- **Key improvement**: Uses script-runner container to avoid circular imports
- **Compatibility**: All existing tests work with minimal changes

The infrastructure is complete and working. Any test failures are typically due to:

1. Missing or incorrect test tags
2. Import issues (easily fixed with proper base class imports)
3. Test data conflicts (solved with factory pattern)

## Technical Details

For implementation details, see:

- [Test Runner Guide](TEST_RUNNER_GUIDE.md) - Architecture and advanced usage
- [@docs/agents/scout.md](agents/scout.md) - Test writing patterns and templates

The test system is built on:

- **UV scripts**: Defined in `pyproject.toml`
- **Odoo test tags**: For proper test discovery
- **Docker containers**: Script-runner for isolation
- **Factory pattern**: For reliable test data
- **Base classes**: Simplified test setup and utilities