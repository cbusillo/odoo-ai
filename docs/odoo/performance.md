---
title: Odoo ORM Performance (18)
---


## Overview

This document covers performance optimization techniques for Odoo 18 ORM operations, with practical examples from the product_connect module. These patterns help avoid N+1 queries, optimize database access, and improve overall application performance.

## Table of Contents

- [ORM Performance Fundamentals](#orm-performance-fundamentals)
- [Prefetch and Flush Strategies](#prefetch-and-flush-strategies)
- [Query Optimization Patterns](#query-optimization-patterns)
- [Batch Processing Techniques](#batch-processing-techniques)
- [Index Strategies](#index-strategies)
- [Memory Management](#memory-management)
- [Read Group vs Manual Aggregation](#read-group-vs-manual-aggregation)
- [Performance Anti-Patterns](#performance-anti-patterns)

## ORM Performance Fundamentals

### Understanding the ORM Cache

Odoo's ORM includes sophisticated caching mechanisms:

```python
# Cache is populated on first access
motors = self.env['motor'].search([('active', '=', True)])

# Subsequent field access uses cache
for motor in motors:
    print(motor.name)  # No DB query - cached
    print(motor.horsepower)  # No DB query - cached
```

### Prefetch Optimization

**Good Practice from product_connect:**
```python
@api.depends("products_not_enabled.reference_product", "products_not_enabled.reference_product.image_256")
def _compute_motor_image(self):
    """Optimized computed field with proper prefetch."""
    # Prefetch related fields in batches
    self.mapped('products_not_enabled.reference_product.image_256')
    
    for motor in self:
        enabled_products = motor.products_not_enabled.filtered('reference_product')
        if enabled_products:
            motor.motor_image = enabled_products[0].reference_product.image_256
        else:
            motor.motor_image = False
```

**Field Prefetch Configuration:**
```python
class Motor(models.Model):
    _name = "motor"
    
    # Fields with prefetch=False for large data
    large_data = fields.Binary(prefetch=False)
    technical_specs = fields.Html(prefetch=False)
    
    # Computed fields with optimized dependencies
    @api.depends("horsepower")
    def _compute_power_rating(self):
        # Single DB query for all records
        for motor in self:
            motor.power_rating = motor.horsepower * 0.746
```

## Prefetch and Flush Strategies

### Controlling Prefetch Behavior

```python
# Disable prefetch for memory-intensive operations
motors = self.env['motor'].with_context(prefetch_fields=False).search([])

# Custom prefetch for specific fields
motors = self.env['motor'].search([])
motors._prefetch_field('name')  # Prefetch only needed fields

# Prefetch related records
motors.mapped('parts.name')  # Triggers prefetch for all motor parts
```

### Strategic Flush Operations

```python
def bulk_motor_update(self, motor_data):
    """Optimized bulk update with controlled flushing."""
    # Disable auto-flush during bulk operations
    with self.env.norecompute():
        for data in motor_data:
            motor = self.env['motor'].browse(data['id'])
            motor.write(data['values'])
    
    # Single flush at the end
    self.env.flush_all()
    
    # Recompute all computed fields once
    self.recompute()
```

### Context-Based Optimization

```python
# Example from product_template.py
def update_inventory_quantity(self, quantity):
    """Update inventory with optimized context."""
    quant = self.stock_quant_ids[0]
    
    # Use inventory_mode to skip unnecessary validations
    quant.with_context(inventory_mode=True).write({"quantity": float(quantity)})
```

## Query Optimization Patterns

### Efficient Search Patterns

**❌ Inefficient:**
```python
# Multiple queries - one per motor
for motor_id in motor_ids:
    motor = self.env['motor'].browse(motor_id)
    parts_count = len(motor.parts)  # Query per motor
```

**✅ Optimized:**
```python
# Single query with read_group
parts_data = self.env['motor.part'].read_group(
    [('motor_id', 'in', motor_ids)],
    ['motor_id'],
    ['motor_id']
)
parts_count_by_motor = {item['motor_id'][0]: item['motor_id_count'] for item in parts_data}
```

### Search vs Browse Optimization

```python
# Use search() for filtering, browse() for known IDs
def get_active_motors(self):
    # Efficient: Single query with domain
    return self.env['motor'].search([('active', '=', True)])

def get_motors_by_ids(self, motor_ids):
    # Efficient: Browse known IDs
    return self.env['motor'].browse(motor_ids)

# Combined approach for complex filtering
def get_filtered_motors(self, complex_domain):
    # Search for IDs first, then browse for efficiency
    motor_ids = self.env['motor'].search(complex_domain).ids
    return self.env['motor'].browse(motor_ids)
```

### Limit and Offset Optimization

```python
def paginated_motor_search(self, page=1, page_size=50):
    """Efficient pagination with proper indexing."""
    offset = (page - 1) * page_size
    
    # Use limit and offset for large datasets
    motors = self.env['motor'].search(
        [('active', '=', True)],
        limit=page_size,
        offset=offset,
        order='create_date desc'  # Ensure consistent ordering
    )
    
    # Get total count efficiently
    total_count = self.env['motor'].search_count([('active', '=', True)])
    
    return {
        'motors': motors,
        'total': total_count,
        'page': page,
        'pages': (total_count + page_size - 1) // page_size
    }
```

## Batch Processing Techniques

### Bulk Create Operations

```python
@api.model_create_multi
def create(self, vals_list):
    """Optimized bulk create from motor.py."""
    # Validate all records before creating any
    for vals in vals_list:
        self._validate_motor_data(vals)
    
    # Single bulk create
    motors = super().create(vals_list)
    
    # Batch post-processing
    self._batch_process_new_motors(motors)
    
    return motors

def _batch_process_new_motors(self, motors):
    """Efficient post-processing for new motors."""
    # Batch operations instead of individual processing
    motor_data = motors.read(['id', 'motor_number', 'manufacturer'])
    
    # Bulk create related records
    part_vals_list = []
    for motor_data_item in motor_data:
        part_vals_list.extend(self._generate_default_parts(motor_data_item))
    
    if part_vals_list:
        self.env['motor.part'].create(part_vals_list)
```

### Batch Write Operations

```python
def batch_update_motors(self, motor_updates):
    """Efficient batch updates."""
    # Group updates by common values
    grouped_updates = {}
    for motor_id, values in motor_updates.items():
        key = frozenset(values.items())
        if key not in grouped_updates:
            grouped_updates[key] = []
        grouped_updates[key].append(motor_id)
    
    # Apply each group of updates in batch
    for values, motor_ids in grouped_updates.items():
        motors = self.env['motor'].browse(motor_ids)
        motors.write(dict(values))
```

### Efficient Unlink Operations

```python
def bulk_archive_motors(self, motor_ids):
    """Efficiently archive instead of deleting."""
    # Archive is faster than unlink for large datasets
    motors = self.env['motor'].browse(motor_ids)
    
    # Batch archive operation
    motors.write({'active': False})
    
    # Archive related records in batches
    related_parts = self.env['motor.part'].search([('motor_id', 'in', motor_ids)])
    related_parts.write({'active': False})
```

## Index Strategies

### Database Index Optimization

```python
class Motor(models.Model):
    _name = "motor"
    
    # Indexed fields for frequent searches
    motor_number = fields.Char(required=True, index=True)
    manufacturer = fields.Char(index=True)
    model = fields.Char(index=True)
    
    # Composite indexes via SQL constraints
    _sql_constraints = [
        ('motor_number_unique', 'unique(motor_number)', 'Motor number must be unique'),
    ]

class MotorStage(models.Model):
    _name = "motor.stage"
    _order = "sequence"
    
    # Index on order field
    sequence = fields.Integer(default=10, index=True)
    name = fields.Char(required=True, index=True)
```

### Search-Optimized Field Design

```python
# Use selection fields instead of char for frequent filtering
class Motor(models.Model):
    _name = "motor"
    
    # Indexed selection for fast filtering
    stage_id = fields.Many2one('motor.stage', index=True)
    
    # Computed field with store=True for searching
    @api.depends("motor_number", "manufacturer", "model", "year")
    def _compute_display_name(self):
        for motor in self:
            motor.display_name = f"{motor.manufacturer} {motor.model} ({motor.year})"
    
    display_name = fields.Char(compute="_compute_display_name", store=True, index=True)
```

### Multi-Column Index Strategies

```python
# Use database-level indexes for complex queries
def _auto_init(self):
    super()._auto_init()
    
    # Create composite index for frequent query patterns
    self._cr.execute("""
        CREATE INDEX IF NOT EXISTS motor_search_idx 
        ON motor (manufacturer, model, year, active)
        WHERE active = true
    """)
    
    # Partial index for active records only
    self._cr.execute("""
        CREATE INDEX IF NOT EXISTS motor_active_stage_idx 
        ON motor (stage_id, create_date) 
        WHERE active = true
    """)
```

## Memory Management

### Large Dataset Processing

```python
def process_large_motor_dataset(self):
    """Process large datasets without memory issues."""
    batch_size = 1000
    offset = 0
    
    while True:
        # Process in chunks to avoid memory issues
        motors = self.env['motor'].search(
            [('active', '=', True)],
            limit=batch_size,
            offset=offset
        )
        
        if not motors:
            break
        
        # Process current batch
        self._process_motor_batch(motors)
        
        # Clear cache to free memory
        self.env.clear()
        
        offset += batch_size

def _process_motor_batch(self, motors):
    """Process a single batch of motors."""
    # Read only needed fields to minimize memory usage
    motor_data = motors.read(['id', 'motor_number', 'horsepower'])
    
    for data in motor_data:
        # Process individual motor data
        self._update_motor_statistics(data)
```

### Cache Management

```python
def memory_efficient_computation(self):
    """Manage cache for memory-intensive operations."""
    # Clear cache before large operations
    self.env.clear()
    
    # Disable prefetch for specific operations
    with self.env.norecompute():
        for motor in self.with_context(prefetch_fields=False):
            # Process without cache
            self._process_motor_without_cache(motor)
    
    # Selective cache invalidation
    self.invalidate_cache(['computed_field_1', 'computed_field_2'])
```

## Read Group vs Manual Aggregation

### Efficient Aggregation with read_group

**❌ Inefficient Manual Aggregation:**
```python
def get_motor_stats_slow(self):
    """Slow manual aggregation - avoid this pattern."""
    manufacturers = self.env['motor'].search([]).mapped('manufacturer')
    stats = {}
    
    for manufacturer in set(manufacturers):
        motors = self.env['motor'].search([('manufacturer', '=', manufacturer)])
        stats[manufacturer] = {
            'count': len(motors),
            'total_hp': sum(motors.mapped('horsepower'))
        }
    
    return stats
```

**✅ Optimized with read_group:**
```python
def get_motor_stats_fast(self):
    """Fast aggregation using read_group."""
    # Single query for all statistics
    stats = self.env['motor'].read_group(
        domain=[('active', '=', True)],
        fields=['manufacturer', 'horsepower:sum'],
        groupby=['manufacturer']
    )
    
    return {
        item['manufacturer']: {
            'count': item['manufacturer_count'],
            'total_hp': item['horsepower']
        }
        for item in stats
    }
```

### Complex Aggregations

```python
def get_detailed_motor_analytics(self):
    """Complex analytics with multiple groupings."""
    # Multi-level grouping
    by_manufacturer_year = self.env['motor'].read_group(
        domain=[('active', '=', True)],
        fields=['manufacturer', 'year', 'horsepower:avg', 'horsepower:max'],
        groupby=['manufacturer', 'year']
    )
    
    # Stage-based analytics
    by_stage = self.env['motor'].read_group(
        domain=[('active', '=', True)],
        fields=['stage_id', 'horsepower:avg'],
        groupby=['stage_id']
    )
    
    return {
        'by_manufacturer_year': by_manufacturer_year,
        'by_stage': by_stage
    }
```

### Conditional Aggregations

```python
def get_conditional_stats(self):
    """Aggregations with complex conditions."""
    # Use SQL aggregation for complex conditions
    query = """
        SELECT 
            manufacturer,
            COUNT(*) as total_count,
            COUNT(*) FILTER (WHERE horsepower > 100) as high_power_count,
            AVG(horsepower) as avg_horsepower,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY horsepower) as median_hp
        FROM motor 
        WHERE active = true 
        GROUP BY manufacturer
        HAVING COUNT(*) > 5
    """
    
    self._cr.execute(query)
    return self._cr.dictfetchall()
```

## Performance Anti-Patterns

### 1. N+1 Query Problem

**❌ N+1 Queries:**
```python
def get_motor_part_counts_slow(self):
    """Generates N+1 queries - avoid this!"""
    motors = self.env['motor'].search([])
    
    for motor in motors:  # Query 1: Get motors
        part_count = len(motor.parts)  # Query N: One per motor
        print(f"Motor {motor.name} has {part_count} parts")
```

**✅ Optimized Solution:**
```python
def get_motor_part_counts_fast(self):
    """Single query solution."""
    # Get part counts in one query
    part_counts = self.env['motor.part'].read_group(
        [('motor_id', '!=', False)],
        ['motor_id'],
        ['motor_id']
    )
    
    count_by_motor = {
        item['motor_id'][0]: item['motor_id_count'] 
        for item in part_counts
    }
    
    motors = self.env['motor'].search([])
    for motor in motors:
        part_count = count_by_motor.get(motor.id, 0)
        print(f"Motor {motor.name} has {part_count} parts")
```

### 2. Inefficient Exists Checks

**❌ Inefficient:**
```python
def check_motor_has_parts_slow(self, motor_id):
    motor = self.env['motor'].browse(motor_id)
    return len(motor.parts) > 0  # Loads all parts
```

**✅ Optimized:**
```python
def check_motor_has_parts_fast(self, motor_id):
    return bool(self.env['motor.part'].search_count([
        ('motor_id', '=', motor_id)
    ], limit=1))  # Stops at first match
```

### 3. Unnecessary Field Loading

**❌ Loading All Fields:**
```python
def get_motor_summary_slow(self):
    motors = self.env['motor'].search([])  # Loads all fields
    return [{'name': m.name, 'number': m.motor_number} for m in motors]
```

**✅ Load Only Needed Fields:**
```python
def get_motor_summary_fast(self):
    motor_data = self.env['motor'].search_read(
        [],
        ['name', 'motor_number']  # Only load needed fields
    )
    return motor_data
```

### 4. Inefficient Computed Fields

**❌ Inefficient Computed Field:**
```python
@api.depends('parts')
def _compute_parts_summary_slow(self):
    for motor in self:
        # Separate query for each motor
        parts = self.env['motor.part'].search([('motor_id', '=', motor.id)])
        motor.parts_summary = f"{len(parts)} parts"
```

**✅ Optimized Computed Field:**
```python
@api.depends('parts')
def _compute_parts_summary_fast(self):
    # Single query for all motors
    part_counts = self.env['motor.part'].read_group(
        [('motor_id', 'in', self.ids)],
        ['motor_id'],
        ['motor_id']
    )
    
    count_by_motor = {
        item['motor_id'][0]: item['motor_id_count']
        for item in part_counts
    }
    
    for motor in self:
        count = count_by_motor.get(motor.id, 0)
        motor.parts_summary = f"{count} parts"
```

## Performance Monitoring

### Query Profiling

```python
import time
from odoo.tools import profile

class Motor(models.Model):
    _name = "motor"
    
    @profile
    def performance_critical_method(self):
        """Profile this method's performance."""
        start_time = time.time()
        
        # Your code here
        result = self._do_complex_operation()
        
        duration = time.time() - start_time
        _logger.info(f"Operation took {duration:.2f} seconds")
        
        return result
```

### Database Query Logging

```python
# Enable query logging in development
def debug_query_performance(self):
    """Debug database queries."""
    # Log queries for analysis
    with self.env.cr.savepoint():
        self._cr._obj.queries = []  # Reset query log
        
        # Your code to analyze
        self._perform_operation()
        
        # Analyze queries
        queries = self._cr._obj.queries
        _logger.info(f"Executed {len(queries)} queries")
        
        for query in queries[-10:]:  # Log last 10 queries
            _logger.info(f"Query: {query['query'][:100]}...")
```

## Performance Checklist

Before deploying performance-critical code:

- [ ] Use `@api.model_create_multi` for bulk creates
- [ ] Implement proper field prefetching
- [ ] Use `read_group()` instead of manual aggregation
- [ ] Add database indexes for frequently searched fields
- [ ] Use `search_read()` when only specific fields are needed
- [ ] Implement batch processing for large datasets
- [ ] Use `search_count()` for existence checks
- [ ] Profile critical operations
- [ ] Clear cache appropriately in long-running operations
- [ ] Use proper ordering in paginated queries

## Additional Resources

- [Odoo Performance Guidelines](https://www.odoo.com/documentation/18.0/developer/reference/backend/performance.html)
- [ORM API Reference](https://www.odoo.com/documentation/18.0/developer/reference/backend/orm.html)
- [Database Performance Tuning](https://www.postgresql.org/docs/current/performance-tips.html)
