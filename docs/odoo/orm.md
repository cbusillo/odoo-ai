Title: Odoo ORM Patterns (18)

## New Decorators and APIs

### @api.model_create_multi

**New in Odoo 18** - Optimized for bulk record creation:

```python
@api.model_create_multi
def create(self, vals_list):
    """Efficiently create multiple records in one operation."""
    # Process all values at once for better performance
    for vals in vals_list:
        if 'name' not in vals:
            vals['name'] = self.env['ir.sequence'].next_by_code('product.code')
    
    # Bulk operations before creation
    self._validate_bulk_data(vals_list)
    
    records = super().create(vals_list)
    
    # Bulk operations after creation
    records._compute_bulk_prices()
    
    return records
```

### Context Keys

**Critical context flags in Odoo 18:**

```python
# Skip all recomputations
with self.env.cr.savepoint():
    self.with_context(recompute=False).write(vals)

# Batch operations
self.with_context(
    prefetch_fields=False,   # Disable prefetching (advanced; measure impact)
    no_reset_password=True,  # Skip password reset emails where supported
    tracking_disable=True,   # Disable mail tracking
).create(vals_list)
```

### New Field Types and Parameters

```python
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # New in Odoo 18: JSON field with schema validation
    specifications = fields.Json(
        string="Product Specifications",
        default={},
        help="JSON storage for flexible product attributes"
    )
    
    # Properties field for dynamic attributes
    dynamic_properties = fields.Properties(
        definition='product_properties_definition',
        copy=True
    )
    
    # Improved HTML field with sanitization
    description_sale = fields.Html(
        sanitize=True,
        sanitize_tags=True,
        sanitize_attributes=True,
        sanitize_style=True,
        strip_style=True,
        strip_classes=True
    )
```

## ORM Performance Improvements

### Flush and Invalidate Patterns

```python
def process_large_dataset(self):
    """Efficient processing of large datasets in Odoo 18."""
    
    # Manual flush control for performance
    for batch in self._get_batches(1000):
        for record in batch:
            record.process_single()
        
        # Flush to database every batch
        self.env.cr.flush()
        
        # Clear caches to prevent memory bloat (Odoo 18)
        self.env.invalidate_all()
    
    # Final flush and clear
    self.env.cr.flush()
    self.env.invalidate_all()
```

### Prefetch Optimization

```python
def optimized_read(self, record_ids):
    """Use prefetch to optimize read operations."""
    
    records = self.browse(record_ids)
    
    # Prefetch related fields in one query
    records.mapped('partner_id.country_id.code')
    
    # Process with prefetched data
    for record in records:
        # These won't trigger additional queries
        country = record.partner_id.country_id
        code = country.code
```

### Read Group Enhancements

```python
def get_statistics(self):
    """Leverage read_group for efficient aggregation."""
    
    # Multiple aggregations in one query
    result = self.env['sale.order'].read_group(
        domain=[('state', '=', 'sale')],
        fields=['partner_id', 'amount_total:sum', 'id:count'],
        groupby=['partner_id', 'date_order:month'],
        lazy=False  # Get all groups at once
    )
    
    # Process aggregated data
    return {
        (r['partner_id'][0], r['date_order:month']): {
            'total': r['amount_total'],
            'count': r['id_count']
        }
        for r in result
    }
```

## Computed Fields Best Practices

### Efficient Dependencies

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    # Use specific field paths to minimize recomputation
    @api.depends('order_line.price_subtotal')
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(order.order_line.mapped('price_subtotal'))
    
    # Context-dependent computation
    @api.depends_context('company', 'allowed_company_ids')
    def _compute_currency_rate(self):
        """Recompute when company context changes."""
        for record in self:
            record.currency_rate = record._get_currency_rate()
    
    # Avoid dependencies on computed fields
    @api.depends('product_id.lst_price')  # Good - stored field
    # @api.depends('product_id.total_cost')  # Bad - computed field
    def _compute_margin(self):
        pass
```

### Store and Compute Patterns

```python
# Stored computed field with search
profit_margin = fields.Float(
    compute='_compute_profit_margin',
    store=True,
    index=True,  # Enable searching
    compute_sudo=True  # Compute with elevated privileges
)

@api.depends('sale_price', 'cost_price')
def _compute_profit_margin(self):
    for record in self:
        if record.sale_price:
            record.profit_margin = (
                (record.sale_price - record.cost_price) / record.sale_price * 100
            )
        else:
            record.profit_margin = 0.0
```

## Constraint Patterns

### SQL Constraints

```python
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    _sql_constraints = [
        ('sku_unique', 'UNIQUE(default_code)', 
         'SKU must be unique across all products!'),
        ('positive_price', 'CHECK(list_price >= 0)', 
         'Sales price must be positive!'),
        ('valid_sku_format', 
         "CHECK(default_code ~ '^[0-9]{4,8}$' OR type != 'consu')",
         'Consumable products require 4-8 digit numeric SKU!')
    ]
```

### Python Constraints

```python
@api.constrains('default_code', 'type')
def _check_sku_format(self):
    """Validate SKU format for consumable products."""
    for product in self:
        if product.type == 'consu' and product.default_code:
            if not re.match(r'^\d{4,8}$', product.default_code):
                raise ValidationError(
                    _("Consumable product %(name)s requires a 4-8 digit numeric SKU. "
                      "Current SKU: %(sku)s",
                      name=product.name,
                      sku=product.default_code)
                )

@api.constrains('motor_ids')
def _check_motor_compatibility(self):
    """Ensure motor compatibility rules."""
    for product in self:
        if len(product.motor_ids) > 1:
            # Check for conflicting motor types
            motor_types = product.motor_ids.mapped('type')
            if len(set(motor_types)) > 1:
                raise ValidationError(
                    _("Product cannot be compatible with different motor types")
                )
```

## Method Decorators

### Onchange vs Depends

```python
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    # Onchange for UI interactions (not called in code)
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update fields when product changes in UI."""
        if self.product_id:
            self.name = self.product_id.get_product_multiline_description_sale()
            self.price_unit = self.product_id.lst_price
    
    # Computed for automatic updates (works in code and UI)
    @api.depends('product_id')
    def _compute_price_unit(self):
        """Always keep price synchronized."""
        for line in self:
            if line.product_id:
                line.price_unit = line.product_id.lst_price
```

### Model Methods

```python
@api.model
def default_get(self, fields_list):
    """Override default values for new records."""
    defaults = super().default_get(fields_list)
    defaults['company_id'] = self.env.company.id
    return defaults

@api.model
def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
    """Override search to add default filters."""
    if not self.env.context.get('show_archived'):
        domain = [('active', '=', True)] + domain
    return super()._search(domain, offset, limit, order, access_rights_uid)
```

## Version Notes

Use `sudo()` deliberately and minimally when privilege is required; there is no
generic `suspend_security()` API. Prefer transactional blocks with
`with self.env.cr.savepoint():` over manual commits. Check Odoo release notes
for any deprecations that affect your module version when migrating.

## Best Practices Summary

1. **Use @api.model_create_multi** for bulk creation
2. **Leverage flush() and invalidate()** for large operations
3. **Optimize with prefetch** for related field access
4. **Use read_group** instead of manual aggregation
5. **Avoid computed field dependencies** in other computed fields
6. **Add indexes** to stored computed fields used in searches
7. **Use SQL constraints** for simple validations
8. **Implement Python constraints** for complex business rules
9. **Prefer computed fields** over onchange for consistency
10. **Handle migration** with compatibility layers
