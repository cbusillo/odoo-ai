Title: Test Scenarios (Common)

Common testing scenarios and solutions.

## Testing Model Methods

### Compute Methods

```python
def test_display_name_compute(self):
    """Test that display_name updates with dependencies."""
    motor = self.env['motor.product'].create({
        'name': 'Yamaha Motor',
        'default_code': '12345678',
        'year': '2023',
        'horsepower': '250',
    })
    
    # Change dependency
    motor.year = '2024'
    motor.flush_recordset()  # Force compute
    
    self.assertIn('2024', motor.display_name)
```

### Onchange Methods

```python
def test_partner_onchange(self):
    """Test onchange populates address fields."""
    order = self.env['sale.order'].new({
        'partner_id': self.test_partner.id,
    })
    order._onchange_partner_id()
    
    self.assertEqual(order.partner_invoice_id, self.test_partner)
    self.assertEqual(order.partner_shipping_id, self.test_partner)
```

### CRUD Operations

```python
def test_product_crud(self):
    """Test Create, Read, Update, Delete operations."""
    # Create
    product = self.env['product.template'].create({
        'name': 'Test Product',
        'default_code': '1234',
    })
    self.assertTrue(product.id)
    
    # Read
    product_read = self.env['product.template'].browse(product.id)
    self.assertEqual(product_read.name, 'Test Product')
    
    # Update
    product.write({'name': 'Updated Product'})
    self.assertEqual(product.name, 'Updated Product')
    
    # Delete
    product.unlink()
    self.assertFalse(product.exists())
```

## Testing Business Logic

### State Transitions

```python
def test_order_state_flow(self):
    """Test order moves through states correctly."""
    order = self.create_test_order()
    
    # Draft → Confirmed
    self.assertEqual(order.state, 'draft')
    order.action_confirm()
    self.assertEqual(order.state, 'sale')
    
    # Check side effects
    self.assertTrue(order.picking_ids)
    self.assertTrue(order.invoice_ids)
```

### Access Rights

```python
def test_user_access(self):
    """Test different user access levels."""
    # Create as admin
    product = self.env['product.template'].create({
        'name': 'Admin Product',
        'default_code': '1234',
    })
    
    # Try to read as portal user
    product_as_portal = product.with_user(self.portal_user)
    with self.assertRaises(AccessError):
        product_as_portal.write({'name': 'Hacked!'})
```

### Multi-Company

```python
def test_multi_company(self):
    """Test multi-company scenarios."""
    # Create in company A
    product_a = self.env['product.template'].with_company(self.company_a).create({
        'name': 'Company A Product',
        'default_code': '1234',
    })
    
    # Verify not visible in company B
    products_b = self.env['product.template'].with_company(self.company_b).search([])
    self.assertNotIn(product_a, products_b)
```

## Testing External Integrations

### API Sync Tests

```python
@patch('requests.post')
def test_shopify_product_sync(self, mock_post):
    """Test syncing product to Shopify."""
    # Mock Shopify response
    mock_post.return_value.json.return_value = {
        'product': {
            'id': 123456,
            'title': 'Test Product',
        }
    }
    
    # Trigger sync
    self.test_product.sync_to_shopify()
    
    # Verify
    self.assertEqual(self.test_product.shopify_product_id, '123456')
    mock_post.assert_called_once()
```

### Webhook Processing

```python
def test_webhook_product_update(self):
    """Test processing Shopify webhook."""
    webhook_data = {
        'id': 123456,
        'title': 'Updated Product',
        'variants': [{
            'sku': '1234',
            'price': '99.99',
        }]
    }
    
    self.env['shopify.webhook'].process_product_update(webhook_data)
    
    product = self.env['product.template'].search([
        ('default_code', '=', '1234')
    ])
    self.assertEqual(product.name, 'Updated Product')
    self.assertEqual(product.list_price, 99.99)
```

## Performance Testing

### Large Dataset Tests

```python
def test_bulk_operations(self):
    """Test performance with large datasets."""
    # Create many products
    products = self.env['product.template']
    for i in range(1000):
        products |= self.env['product.template'].create({
            'name': f'Product {i}',
            'default_code': f'{i:08d}',
        })
    
    # Test bulk operation
    start_time = time.time()
    products.write({'active': False})
    duration = time.time() - start_time
    
    # Should complete in reasonable time
    self.assertLess(duration, 5.0)  # 5 seconds max
```

## Error Handling Tests

### Expected Errors

```python
def test_validation_errors(self):
    """Test that validation errors are raised correctly."""
    with self.assertRaisesRegex(ValidationError, "SKU must be"):
        self.env['product.template'].create({
            'name': 'Bad Product',
            'default_code': 'INVALID!',
            'type': 'consu',
        })
```

### Rollback Behavior

```python
def test_transaction_rollback(self):
    """Test that errors rollback the transaction."""
    with self.assertRaises(ValidationError):
        with self.cr.savepoint():
            # This should succeed
            product = self.env['product.template'].create({
                'name': 'Good Product',
                'default_code': '1234',
            })
            
            # This should fail and rollback everything
            self.env['product.template'].create({
                'name': 'Bad Product',
                'default_code': 'BAD',
            })
    
    # Verify rollback
    products = self.env['product.template'].search([
        ('name', '=', 'Good Product')
    ])
    self.assertFalse(products)
```
