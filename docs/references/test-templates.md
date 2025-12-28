---
title: Test Templates
---


Detailed test patterns and examples for Scout agent.

## Python Unit Test Templates

### Basic Model Test

```python
from odoo.tests import tagged
from odoo.addons.product_connect.tests.fixtures.test_base import ProductConnectTransactionCase

@tagged("post_install", "-at_install")
class TestMotorProduct(ProductConnectTransactionCase):
    def test_motor_creation(self):
        """Test creating a motor product with all required fields."""
        motor = self.env['motor.product'].create({
            'name': 'Test Motor',
            'default_code': '12345678',  # Valid SKU
            'brand_id': self.test_brand.id,
            'year': '2023',
            'horsepower': '250',
        })
        self.assertEqual(motor.display_name, 'Test Motor - 2023 Test Brand 250HP')
```

### Testing Computed Fields

```python
def test_compute_method(self):
    """Test that computed fields update correctly."""
    # Trigger compute
    self.test_product.invalidate_recordset(['computed_field'])
    # Force recomputation
    self.assertEqual(self.test_product.computed_field, expected_value)
```

### Testing Constraints

```python
def test_sku_constraint(self):
    """Test SKU validation constraint."""
    with self.assertRaisesRegex(ValidationError, "SKU must be"):
        self.env['product.template'].create({
            'name': 'Invalid Product',
            'default_code': 'ABC',  # Invalid SKU
            'type': 'consu',
        })
```

### Testing Wizards

```python
def test_import_wizard(self):
    """Test the import wizard flow."""
    wizard = self.env['shopify.import.wizard'].create({
        'import_type': 'products',
        'date_from': '2024-01-01',
    })
    wizard.action_import()
    self.assertTrue(wizard.import_complete)
```

## Mocking Patterns

### Mock External APIs

```python
from unittest.mock import patch, MagicMock
from ..services.shopify.client import ShopifyClient

class TestShopifySync(ProductConnectTransactionCase):
    @patch.object(ShopifyClient, 'execute')
    def test_product_sync(self, mock_execute):
        mock_execute.return_value = {
            'data': {
                'product': {
                    'id': 'gid://shopify/Product/123',
                    'title': 'Test Product',
                    'variants': {'edges': []}
                }
            }
        }
        result = self.test_product.sync_to_shopify()
        self.assertTrue(result)
        mock_execute.assert_called_once()
```

### Mock Odoo Methods

```python
@patch.object(type(self.env['product.template']), 'search')
def test_with_search_mock(self, mock_search):
    mock_search.return_value = self.test_products
    result = self.env['some.model'].process_products()
    mock_search.assert_called_with([('type', '=', 'product')])
```

## Integration Test Patterns

### Testing with Context

```python
def test_skip_shopify_sync(self):
    """Test that context flag prevents Shopify sync."""
    # Context is pre-set in base class
    product = self.env['product.template'].create({
        'name': 'No Sync Product',
        'default_code': '1234',
    })
    # No sync should happen due to skip_shopify_sync=True
    self.assertFalse(product.shopify_product_id)
```

### Testing Workflows

```python
def test_order_workflow(self):
    """Test complete order workflow."""
    # Create order
    order = self.env['sale.order'].create({
        'partner_id': self.test_partner.id,
    })
    
    # Add line
    self.env['sale.order.line'].create({
        'order_id': order.id,
        'product_id': self.test_product.id,
        'product_uom_qty': 2,
    })
    
    # Confirm order
    order.action_confirm()
    self.assertEqual(order.state, 'sale')
    
    # Check stock moves created
    self.assertTrue(order.picking_ids)
```

## Common Test Helpers

### Custom Assertions

```python
def assertProductValid(self, product):
    """Custom assertion for product validity."""
    self.assertTrue(product.default_code)
    self.assertRegex(product.default_code, r'^\d{4,8}$')
    self.assertTrue(product.name)
    self.assertIn(product.type, ['consu', 'service'])
```

### Test Data Factories

```python
def create_test_order(self, lines=1):
    """Helper to create test orders."""
    order = self.env['sale.order'].create({
        'partner_id': self.test_partner.id,
    })
    for i in range(lines):
        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.test_products[i].id,
            'product_uom_qty': 1,
        })
    return order
```
