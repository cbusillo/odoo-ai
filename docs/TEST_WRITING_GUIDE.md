# Test Writing Guide

This guide covers how to write effective tests for the Odoo 18 project using our modern test infrastructure.

## Quick Start

### 1. Choose the Right Test Type

```python
# Fast business logic tests
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase

@tagged(*UNIT_TAGS)
class TestBusinessLogic(UnitTestCase):
    def test_motor_creation(self):
        # Fast, isolated test
        pass

# Service integration tests
from ..common_imports import tagged, INTEGRATION_TAGS
from ..fixtures import IntegrationTestCase

@tagged(*INTEGRATION_TAGS)
class TestShopifySync(IntegrationTestCase):
    def test_product_sync(self):
        # Real service integration
        pass

# Browser workflow tests
from ..common_imports import tagged, TOUR_TAGS
from ..fixtures import TourTestCase

@tagged(*TOUR_TAGS)
class TestProductWorkflow(TourTestCase):
    def test_product_creation_flow(self):
        # End-to-end browser test
        pass
```

### 2. Use Factory Pattern

```python
from ..fixtures import ProductFactory, PartnerFactory

# ✅ GOOD - Always unique
product = ProductFactory.create(self.env, name="Custom Name")

# ❌ BAD - Will cause conflicts
product = self.env["product.template"].create({
    "default_code": "TEST001",  # Conflicts!
})
```

## Test Tagging System

### Tag Constants (Required)

All tests MUST use tag constants from `base_types.py`:

```python
# Import the constants
from ..common_imports import tagged, UNIT_TAGS, INTEGRATION_TAGS, TOUR_TAGS

# Use them with @tagged decorator
@tagged(*UNIT_TAGS)          # Unit tests
@tagged(*INTEGRATION_TAGS)   # Integration tests  
@tagged(*TOUR_TAGS)          # Tour tests
```

### Tag Definitions

```python
# From base_types.py
STANDARD_TAGS = ["post_install", "-at_install"]
UNIT_TAGS = STANDARD_TAGS + ["unit_test"]
INTEGRATION_TAGS = STANDARD_TAGS + ["integration_test"]
TOUR_TAGS = STANDARD_TAGS + ["tour_test"]
```

### Why Use Constants?

- **Consistency**: Same tags across all tests
- **Discovery**: Test runner finds tests properly
- **Maintenance**: Change tags in one place
- **Type safety**: IDE autocomplete and validation

## Base Test Classes

### UnitTestCase

**Purpose**: Fast, isolated business logic tests

**Features**:
- Fresh database per test class
- Mock support for external services
- Factory pattern for test data
- No external dependencies

**Example**:

```python
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase, ProductFactory

@tagged(*UNIT_TAGS)
class TestMotorModel(UnitTestCase):
    def test_motor_creation(self):
        motor = ProductFactory.create_motor(self.env)
        self.assertEqual(motor.product_type, "motor")
        
    def test_validation_rules(self):
        with self.assertRaises(ValidationError):
            ProductFactory.create(self.env, default_code="")
```

### IntegrationTestCase

**Purpose**: Service layer and API integration tests

**Features**:
- Stable test database with snapshots
- Pre-configured mock services
- Real integration testing capabilities
- Shared setup for efficiency

**Example**:

```python
from ..common_imports import tagged, INTEGRATION_TAGS
from ..fixtures import IntegrationTestCase

@tagged(*INTEGRATION_TAGS)
class TestShopifySync(IntegrationTestCase):
    def test_product_sync(self):
        # Create test credentials
        credentials = self.create_shopify_credentials()
        
        # Mock external service
        with self.mock_shopify_client() as mock_client:
            mock_client.query.return_value = self.mock_shopify_response({
                "products": {"edges": []}
            })
            
            # Test the service
            result = self.shopify_service.sync_products()
            self.assertTrue(result.success)
```

### TourTestCase

**Purpose**: Browser-based UI workflow tests

**Features**:
- Full staging environment
- Complete demo data
- Browser automation support
- End-to-end workflow testing

**Example**:

```python
from ..common_imports import tagged, TOUR_TAGS
from ..fixtures import TourTestCase

@tagged(*TOUR_TAGS)
class TestProductWorkflow(TourTestCase):
    def setUp(self):
        super().setUp()
        self.browser_size = "1920x1080"  # MUST be string!
        
    def test_product_creation_flow(self):
        self.start_tour("/odoo", "product_creation_tour")
```

## Factory Pattern Usage

### Available Factories

```python
from ..fixtures import (
    ProductFactory,         # Standard products with unique SKUs
    PartnerFactory,         # Customers/vendors with contacts  
    MotorFactory,          # Motor-specific products
    ShopifyProductFactory, # Products with Shopify metadata
    SaleOrderFactory,      # Orders with line items
)
```

### Basic Usage

```python
# Single record with defaults
product = ProductFactory.create(self.env)

# Single record with custom data
product = ProductFactory.create(self.env, 
    name="Custom Motor",
    list_price=299.99
)

# Multiple records
products = ProductFactory.create_batch(self.env, count=5)

# Complex scenarios
company, contacts = PartnerFactory.create_with_contacts(self.env)
motor = MotorFactory.create_with_variants(self.env, variant_count=3)
```

### Why Use Factories?

**Problem**: Hardcoded test data causes conflicts

```python
# ❌ This will fail when run multiple times
product1 = self.env["product.template"].create({
    "default_code": "TEST001",
    "name": "Test Product"
})

product2 = self.env["product.template"].create({
    "default_code": "TEST001",  # DUPLICATE! Fails
    "name": "Another Product"
})
```

**Solution**: Factories generate unique data

```python
# ✅ Always works - unique every time
product1 = ProductFactory.create(self.env)  # SKU: TEST_20250812_143022_001
product2 = ProductFactory.create(self.env)  # SKU: TEST_20250812_143022_002
```

## Common Pitfalls to Avoid

### 1. Browser Size Format

```python
# ✅ CORRECT - String format
self.browser_size = "1920x1080"

# ❌ WRONG - Tuple format (will fail)
self.browser_size = (1920, 1080)
```

### 2. Missing Imports

```python
# ✅ CORRECT - Import when using
import secrets
def test_random_data(self):
    random_id = secrets.randbelow(1000)

# ❌ WRONG - Using without import (will fail)
def test_random_data(self):
    random_id = secrets.randbelow(1000)  # NameError!
```

### 3. Incorrect Tag Usage

```python
# ✅ CORRECT - Use constants
from ..common_imports import tagged, UNIT_TAGS
@tagged(*UNIT_TAGS)

# ❌ WRONG - Hardcoded strings
@tagged("unit_test", "post_install", "-at_install")
```

### 4. Wrong Import Paths

```python
# ✅ CORRECT - Relative imports
from ..common_imports import tagged, UNIT_TAGS
from ..fixtures import UnitTestCase

# ❌ WRONG - Absolute imports (will fail)
from addons.product_connect.tests.fixtures import UnitTestCase
```

### 5. PyCharm Warnings to Ignore

These PyCharm warnings are **false positives** - ignore them:

- **"odoo.values.*" types**: PyCharm doesn't understand Odoo's type system
- **"Missing type annotations"**: Odoo models don't use standard Python typing
- **"Unused imports"**: Base classes and fixtures are used by the framework

## Test Organization Best Practices

### File Structure

```
addons/product_connect/tests/
├── fixtures/               # Base classes, factories, mocks
│   ├── __init__.py
│   ├── base.py            # Base test classes
│   ├── factories.py       # Test data factories
│   └── shopify_responses.py # Mock response data
├── unit/                  # Fast business logic tests
│   ├── test_model_motor.py
│   ├── test_model_product.py
│   └── test_service_*.py
├── integration/           # Service and API tests
│   ├── test_shopify_sync.py
│   ├── test_import_*.py
│   └── test_service_*.py
└── tour/                  # Browser workflow tests
    ├── test_tour_basic.py
    ├── test_multigraph_*.py
    └── test_workflow_*.py
```

### Test Class Naming

```python
# ✅ GOOD - Clear, descriptive names
class TestMotorModelCreation(UnitTestCase):
class TestShopifyProductSync(IntegrationTestCase):
class TestProductWorkflowTour(TourTestCase):

# ❌ BAD - Vague or unclear
class TestStuff(UnitTestCase):
class Test1(IntegrationTestCase):
```

### Test Method Naming

```python
# ✅ GOOD - Describes what's being tested
def test_motor_creation_with_valid_data(self):
def test_shopify_sync_handles_api_errors(self):
def test_product_workflow_end_to_end(self):

# ❌ BAD - Unclear what's being tested
def test_1(self):
def test_it_works(self):
```

### Test Data Management

```python
# ✅ GOOD - Use factories for uniqueness
def test_duplicate_sku_prevention(self):
    product1 = ProductFactory.create(self.env)
    
    # Try to create duplicate - should fail
    with self.assertRaises(ValidationError):
        ProductFactory.create(self.env, default_code=product1.default_code)

# ✅ GOOD - Use class-level data for shared setup
@classmethod
def setUpClass(cls):
    super().setUpClass()
    cls.test_company = cls.env.ref("base.main_company")
    cls.test_warehouse = WarehouseFactory.create(cls.env)

# ❌ BAD - Hardcoded data that conflicts
def test_product_creation(self):
    product = self.env["product.template"].create({
        "default_code": "MOTOR001",  # Will conflict!
        "name": "Test Motor"
    })
```

## Running Your Tests

### During Development

```bash
# Quick feedback loop
uv run test-unit           # Run your unit tests (< 2 min)

# Test specific area
uv run test-integration    # Integration tests (< 10 min)

# Full validation
uv run test-all           # Everything (< 30 min)
```

### Debugging Test Issues

```bash
# See what tests are discovered
uv run test-stats

# Check for problems
uv run test-clean          # Clean artifacts
uv run test-setup          # Reinitialize databases
```

### Test Output

```bash
# Normal run - shows progress
uv run test-unit

# For CI/detailed logs, check:
# tmp/tests/unit_tests.log
# tmp/tests/integration_tests.log
# tmp/tests/tour_tests.log
```

## Common Test Patterns

### Testing Model Validation

```python
@tagged(*UNIT_TAGS)
class TestMotorValidation(UnitTestCase):
    def test_required_fields(self):
        with self.assertRaises(ValidationError):
            MotorFactory.create(self.env, name="")
            
    def test_unique_constraints(self):
        motor1 = MotorFactory.create(self.env)
        
        with self.assertRaises(ValidationError):
            MotorFactory.create(self.env, default_code=motor1.default_code)
```

### Testing Service Integration

```python
@tagged(*INTEGRATION_TAGS)
class TestShopifyService(IntegrationTestCase):
    def test_product_sync_success(self):
        credentials = self.create_shopify_credentials()
        
        with self.mock_shopify_client() as client:
            client.query.return_value = self.mock_shopify_response({
                "products": {"edges": [{"node": {"id": "123"}}]}
            })
            
            service = ShopifyService(credentials)
            result = service.sync_products()
            
            self.assertTrue(result.success)
            self.assertEqual(len(result.products), 1)
            
    def test_api_error_handling(self):
        credentials = self.create_shopify_credentials()
        
        with self.mock_shopify_client() as client:
            client.query.side_effect = Exception("API Error")
            
            service = ShopifyService(credentials)
            result = service.sync_products()
            
            self.assertFalse(result.success)
            self.assertIn("API Error", result.error_message)
```

### Testing Browser Workflows

```python
@tagged(*TOUR_TAGS)
class TestProductCreationTour(TourTestCase):
    def setUp(self):
        super().setUp()
        self.browser_size = "1920x1080"
        
    def test_create_motor_product(self):
        # Tour defined in JS file
        self.start_tour("/odoo", "create_motor_product_tour")
        
    def test_multigraph_view(self):
        # Create test data first
        MotorFactory.create_batch(self.env, count=5)
        
        self.start_tour("/odoo", "multigraph_analysis_tour")
```

## Best Practices Summary

### ✅ DO

- Use tag constants (`UNIT_TAGS`, etc.)
- Use factories for test data
- Import from `common_imports` and `fixtures`
- Use relative imports (`from ..`)
- Make browser_size a string
- Write descriptive test names
- Test one thing per test method
- Use appropriate base classes

### ❌ DON'T

- Hardcode test tags
- Create duplicate test data
- Use absolute imports
- Use tuple for browser_size
- Write vague test names
- Test multiple things in one method
- Mix test types in same class
- Ignore PyCharm's Odoo warnings (they're false positives)

## Getting Help

### Test Discovery Issues

```bash
uv run test-stats  # See what's discovered
```

### Import Problems

```python
# Check your imports match this pattern:
from ..common_imports import tagged, UNIT_TAGS, ValidationError
from ..fixtures import UnitTestCase, ProductFactory
```

### Database Conflicts

```bash
uv run test-clean  # Reset everything
```

### Container Issues

```bash
docker ps | grep script-runner  # Check container status
```

For more details, see the [Test Runner Guide](TEST_RUNNER_GUIDE.md).