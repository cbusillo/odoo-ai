# Performance Optimization Patterns

This file contains detailed performance patterns and examples extracted from the Flash agent documentation.

## Common Performance Anti-Patterns and Solutions

### N+1 Query Patterns

```python
# BAD: N+1 query in loop
for order in orders:
    customer_name = order.partner_id.name  # DB query each iteration!

# GOOD: Prefetch with mapped
customer_names = orders.mapped('partner_id.name')  # Single query

# GOOD: Prefetch specific fields
orders.mapped('partner_id').mapped('name')
```

### Inefficient Computed Fields

```python
# BAD: Search in compute
@api.depends('product_id')
def _compute_stock(self):
    for record in self:
        # Searches for each record!
        record.stock = self.env['stock.quant'].search([
            ('product_id', '=', record.product_id.id)
        ]).quantity

# GOOD: Batch compute
@api.depends('product_id')
def _compute_stock(self):
    stocks = self.env['stock.quant'].read_group(
        [('product_id', 'in', self.mapped('product_id').ids)],
        ['product_id', 'quantity:sum'],
        ['product_id']
    )
    stock_dict = {s['product_id'][0]: s['quantity'] for s in stocks}
    for record in self:
        record.stock = stock_dict.get(record.product_id.id, 0)
```

### Field Storage Optimization

```python
# BAD: Computed on every access
total = fields.Float(compute='_compute_total')

# GOOD: Store when appropriate
total = fields.Float(compute='_compute_total', store=True)
```

## Analysis Guidance

### Comprehensive Performance Analysis

Use Odoo Intelligence performance analysis for hot models (e.g., sale.order.line), inspect field dependencies for
critical computed fields, and sample data distributions to understand edge cases. Keep investigations narrow and convert
findings into small, verifiable patches.

### Find Inefficient Code Patterns

Search for known hotpaths (search in loops, id dereferences in loops, inefficient computed fields) and address them
incrementally (batching, read_group, prefetch, store=True where appropriate).

## Optimization Strategy Patterns

### Batch Operations

```python
# BAD: Individual writes
for record in records:
    record.write({'processed': True})

# GOOD: Batch write
records.write({'processed': True})
```

### Efficient Search Patterns

```python
# BAD: Search then filter
products = self.env['product.template'].search([])
active = products.filtered(lambda p: p.active)

# GOOD: Search with domain
active = self.env['product.template'].search([('active', '=', True)])

# BAD: Get all then slice
all_orders = self.env['sale.order'].search([])
recent = all_orders[:10]

# GOOD: Limit in search
recent = self.env['sale.order'].search([], limit=10)
```

### Strategic SQL Usage

```python
# For complex aggregations where ORM is insufficient
self.env.cr.execute("""
    SELECT partner_id, SUM(amount_total)
    FROM sale_order
    WHERE state = 'sale'
    GROUP BY partner_id
""")
results = self.env.cr.dictfetchall()
```

## Performance Monitoring Patterns

### Query Count Monitoring

```python
# In development environment
initial_count = self.env.cr.sql_log_count
# ... operation ...
final_count = self.env.cr.sql_log_count
queries_executed = final_count - initial_count
_logger.info(f"Operation executed {queries_executed} queries")
```

### Method Profiling

```python
import time

def profile_method(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        _logger.info(f"{func.__name__} took {duration:.2f} seconds")
        return result
    return wrapper

@profile_method
def expensive_computation(self):
    # ... complex logic ...
    pass
```

## Advanced Optimization Patterns

### Batch Computation Strategy

```python
# ✅ FAST: Single query with mapped
partner_names = orders.mapped('partner_id.name')

# ✅ FASTER: Batch compute with grouping
@api.depends('line_ids.price_total')
def _compute_amount_total(self):
    # Group by order for efficiency
    amounts = {}
    for line in self.mapped('line_ids'):
        amounts.setdefault(line.order_id.id, 0)
        amounts[line.order_id.id] += line.price_total
    
    for order in self:
        order.amount_total = amounts.get(order.id, 0)
```

### Strategic Index Implementation

```python
# ✅ INDEX: On frequently searched fields
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    state = fields.Selection(index=True)  # Searched in every view
    date_order = fields.Datetime(index=True)  # Used in filters
    partner_id = fields.Many2one(index=True)  # Foreign key searches
    
    # Don't index rarely searched fields - they slow writes
    notes = fields.Text()  # No index needed
```

### Efficient Search and Count Patterns

```python
# ✅ LIMIT: Don't fetch everything
recent_orders = self.env['sale.order'].search(
    [('state', '=', 'sale')],
    limit=100,
    order='date_order desc'
)

# ✅ SEARCH_COUNT: When you only need the count
total_sales = self.env['sale.order'].search_count([
    ('date_order', '>=', '2024-01-01'),
    ('state', '=', 'sale')
])

# ✅ EXISTS: When checking if any records exist
has_orders = bool(self.env['sale.order'].search(
    [('partner_id', '=', partner.id)],
    limit=1
))
```

### Real-World Optimization Example

```python
# How Odoo optimizes inventory quantity calculations
def _compute_quantities_dict(self, lot_id, owner_id, package_id):
    # ✅ Uses read_group for database-level aggregation
    domain_quant = self._get_domain_locations()
    quants = self.env['stock.quant'].read_group(
        domain_quant,
        ['product_id', 'quantity:sum', 'reserved_quantity:sum'],
        ['product_id'],
        orderby='id'
    )
    # ✅ Builds dictionary for O(1) lookup instead of repeated searches
    return {q['product_id'][0]: q for q in quants}
```

## Performance Testing Patterns

### Before/After Measurement

```python
def performance_test(method, iterations=1000):
    """Test method performance with multiple iterations."""
    import time
    
    # Warm-up
    method()
    
    # Measure
    start = time.time()
    for _ in range(iterations):
        method()
    duration = time.time() - start
    
    return {
        'total_time': duration,
        'avg_time': duration / iterations,
        'operations_per_second': iterations / duration
    }
```

### Memory Usage Tracking

```python
import tracemalloc

def memory_profile(func):
    """Profile memory usage of a function."""
    def wrapper(*args, **kwargs):
        tracemalloc.start()
        
        result = func(*args, **kwargs)
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        _logger.info(f"{func.__name__}: Current={current/1024/1024:.1f}MB, Peak={peak/1024/1024:.1f}MB")
        return result
    return wrapper
```

## Database-Level Optimization Patterns

### Index Strategy Guidelines

1. **Always Index**:
    - Foreign keys used in searches
    - Fields used in WHERE clauses frequently
    - Fields used for ordering in views

2. **Consider Indexing**:
    - Selection fields with limited values
    - Date/datetime fields for filtering
    - Boolean fields used in domains

3. **Avoid Indexing**:
    - Text fields (use search capabilities instead)
    - Fields with high cardinality and rare searches
    - Temporary or computed fields

### Read Group Optimization

```python
# ✅ Efficient aggregation with read_group
def get_sales_by_month(self):
    data = self.env['sale.order'].read_group(
        [('state', '=', 'sale')],
        ['amount_total:sum'],
        ['date_order:month'],
        orderby='date_order:month'
    )
    return [(d['date_order:month'], d['amount_total']) for d in data]

# ❌ Inefficient: Load all records then group in Python
def get_sales_by_month_bad(self):
    orders = self.env['sale.order'].search([('state', '=', 'sale')])
    # Python grouping is much slower than database grouping
    ...
```
