# 🧙 Odoo Engineer - Detailed Framework Patterns

This file contains detailed Odoo framework patterns and examples extracted from the Odoo Engineer agent documentation.

## Research-First Methodology

### Complete Research Workflow

```python
# Step 1: Search for Patterns
def research_odoo_patterns(feature_type):
    # Find existing implementations
    patterns = mcp__odoo-intelligence__search_code(
        pattern=f"widget.*{feature_type}|class.*{feature_type}",
        file_type="xml"  # or "py", "js" as needed
    )
    
    # Get related code patterns  
    py_patterns = mcp__odoo-intelligence__search_code(
        pattern=f"def.*{feature_type}|{feature_type}.*field",
        file_type="py"
    )
    
    return patterns + py_patterns

# Step 2: Deep Structure Analysis
def analyze_odoo_structure(model_name):
    # Understand the complete model
    model_info = mcp__odoo-intelligence__model_query(operation="info", model_name=model_name)
    
    # See how it's used in views
    view_usage = mcp__odoo-intelligence__view_model_usage(model_name=model_name)
    
    # Trace complete inheritance
    inheritance = mcp__odoo-intelligence__model_query(operation="inheritance", model_name=model_name)
    
    # Find performance considerations
    performance = mcp__odoo-intelligence__analysis_query(analysis_type="performance", model_name=model_name)
    
    return {
        'model': model_info,
        'views': view_usage, 
        'inheritance': inheritance,
        'performance': performance
    }

# Step 3: Theory Validation
def validate_theories(test_code):
    # Test assumptions in Odoo shell
    result = mcp__odoo-intelligence__execute_code(code=test_code)
    return result

# Step 4: File-Specific Research
def research_specific_implementations(pattern):
    # Read core Odoo implementations
    core_file = mcp__odoo-intelligence__read_odoo_file(
        file_path=f"sale/views/sale_views.xml",
        pattern=pattern,
        context_lines=10
    )
    
    # Read custom implementations for comparison
    custom_files = mcp__odoo-intelligence__find_files(
        pattern=f"*{pattern}*.xml"
    )
    
    return {'core': core_file, 'custom': custom_files}
```

## Advanced Odoo Patterns

### View Architecture Patterns

```xml
<!-- Multi-graph View Implementation -->
<record id="view_product_multigraph" model="ir.ui.view">
    <field name="name">product.template.multigraph</field>
    <field name="model">product.template</field>
    <field name="type">graph</field>
    <field name="mode">primary</field>
    <field name="inherit_id" ref="web.view_graph"/>
    <field name="arch" type="xml">
        <xpath expr="//graph" position="attributes">
            <attribute name="js_class">multigraph</attribute>
            <attribute name="stacked">True</attribute>
        </xpath>
        <!-- Add multiple measure support -->
        <xpath expr="//graph" position="inside">
            <field name="qty_available" type="measure"/>
            <field name="list_price" type="measure"/>
        </xpath>
    </field>
</record>

<!-- View Button Pattern -->
<record id="action_product_multigraph" model="ir.actions.act_window">
    <field name="name">Product Analysis</field>
    <field name="res_model">product.template</field>
    <field name="view_mode">list,form,graph</field>
    <field name="context">{
        'graph_view': 'multigraph',
        'default_view_type': 'graph'
    }</field>
</record>
```

### Model Mixin Patterns

```python
# Abstract Mixin for Reusable Functionality
class ProductAnalyticsMixin(models.AbstractModel):
    _name = 'product.analytics.mixin'
    _description = 'Product Analytics Mixin'
    
    # Group related fields
    qty_available = fields.Float(
        compute='_compute_quantities',
        store=True,
        help="Quantity available in default location"
    )
    
    turnover_rate = fields.Float(
        compute='_compute_turnover',
        store=True,
        help="Product turnover rate per year"
    )
    
    @api.depends('stock_move_ids.product_qty', 'stock_move_ids.date')
    @api.depends_context('warehouse')
    def _compute_quantities(self):
        # Context-aware computation respecting warehouse context
        for record in self:
            warehouse_id = self.env.context.get('warehouse')
            if warehouse_id:
                # Warehouse-specific calculation
                domain = [
                    ('product_id', '=', record.id),
                    ('location_id.usage', '=', 'internal'),
                    ('location_id.warehouse_id', '=', warehouse_id)
                ]
            else:
                # Default calculation
                domain = [
                    ('product_id', '=', record.id),
                    ('location_id.usage', '=', 'internal')
                ]
            
            quants = self.env['stock.quant'].search(domain)
            record.qty_available = sum(quants.mapped('quantity'))
    
    @api.depends('sale_line_ids.product_uom_qty', 'sale_line_ids.order_id.date_order')
    def _compute_turnover(self):
        # Efficient aggregation using read_group
        for record in self:
            # Get sales data for last 12 months
            cutoff_date = fields.Date.today() - relativedelta(months=12)
            
            sales_data = self.env['sale.order.line'].read_group(
                [
                    ('product_id', '=', record.id),
                    ('order_id.date_order', '>=', cutoff_date),
                    ('order_id.state', 'in', ['sale', 'done'])
                ],
                ['product_uom_qty:sum'],
                []
            )
            
            if sales_data:
                total_sold = sales_data[0]['product_uom_qty']
                avg_stock = record.qty_available or 1  # Avoid division by zero
                record.turnover_rate = total_sold / avg_stock
            else:
                record.turnover_rate = 0.0

# Using the Mixin
class ProductTemplate(models.Model):
    _inherit = ['product.template', 'product.analytics.mixin']
```

### Advanced Performance Patterns

```python
# Batch Processing Pattern
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def update_prices_batch(self):
        """Update prices for multiple orders efficiently."""
        # ✅ GOOD: Single query for all pricelist data
        pricelist_data = {}
        for pricelist in self.mapped('pricelist_id'):
            pricelist_data[pricelist.id] = pricelist.get_products_price(
                self.mapped('order_line.product_id').ids
            )
        
        # ✅ GOOD: Batch update all order lines
        lines_to_update = []
        for order in self:
            pricelist_prices = pricelist_data.get(order.pricelist_id.id, {})
            for line in order.order_line:
                new_price = pricelist_prices.get(line.product_id.id)
                if new_price and new_price != line.price_unit:
                    lines_to_update.append({
                        'id': line.id,
                        'price_unit': new_price
                    })
        
        # ✅ GOOD: Single write operation for all updates
        if lines_to_update:
            self.env['sale.order.line'].browse([l['id'] for l in lines_to_update]).write({
                'price_unit': [l['price_unit'] for l in lines_to_update]
            })

# Memory-Efficient Large Dataset Processing
def process_large_product_dataset(self, domain):
    """Process large datasets without memory issues."""
    batch_size = 1000
    offset = 0
    
    while True:
        products = self.env['product.template'].search(
            domain,
            limit=batch_size,
            offset=offset,
            order='id'
        )
        
        if not products:
            break
            
        # Process batch
        self._process_product_batch(products)
        
        # Clear cache to free memory
        products.invalidate_cache()
        
        offset += batch_size
        
        # Force garbage collection for large datasets
        if offset % 10000 == 0:
            import gc
            gc.collect()
```

### Security and Access Control Patterns

```python
# Comprehensive Security Pattern
class SensitiveModel(models.Model):
    _name = 'sensitive.model'
    _description = 'Model with Security Patterns'
    
    def secure_operation(self, operation_type='read'):
        """Demonstrate proper security checking."""
        # ✅ GOOD: Explicit access rights check
        try:
            self.check_access_rights(operation_type)
            self.check_access_rule(operation_type)
        except AccessError as e:
            raise UserError(_("Access denied: %s") % str(e))
        
        # Document sudo usage with clear reasoning
        if self.env.context.get('bypass_security_for_system'):
            # Why: System operations need to bypass user security
            # Risk: Documented and controlled
            return self.sudo()._perform_system_operation()
        
        return self._perform_user_operation()
    
    def _perform_user_operation(self):
        """Normal user operation respecting security."""
        # Respect record rules automatically
        return self.search([('allowed_user_ids', 'in', self.env.user.id)])
    
    def _perform_system_operation(self):
        """System operation with elevated privileges."""
        # System logic here - documented why sudo is needed
        return self.with_context(active_test=False).search([])
```

### Testing Patterns for Odoo

```python
# Comprehensive Test Pattern
from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError, AccessError

@tagged('post_install', '-at_install')
class TestProductAnalytics(TransactionCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # ✅ GOOD: Use existing data when possible
        cls.product = cls.env.ref('product.product_product_1')
        cls.partner = cls.env.ref('base.res_partner_1')
        
        # ✅ GOOD: Create minimal test data
        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Test Warehouse',
            'code': 'TWH'
        })
    
    def test_quantity_computation(self):
        """Test quantity computation respects warehouse context."""
        # ✅ GOOD: Test with specific context
        product = self.product.with_context(warehouse=self.warehouse.id)
        
        # Create stock
        self.env['stock.quant'].create({
            'product_id': product.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'quantity': 100.0
        })
        
        # Force recomputation
        product._compute_quantities()
        
        self.assertEqual(product.qty_available, 100.0)
    
    def test_security_rules(self):
        """Test access control explicitly."""
        # ✅ GOOD: Create limited user for testing
        test_user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'test_user',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]
        })
        
        # Test access as limited user
        product_as_user = self.product.with_user(test_user)
        
        with self.assertRaises(AccessError):
            product_as_user.write({'list_price': 999.99})
    
    def test_performance_constraints(self):
        """Test performance doesn't degrade with scale."""
        # ✅ GOOD: Create many records to test N+1
        products = []
        for i in range(100):
            products.append({
                'name': f'Test Product {i}',
                'type': 'product'
            })
        
        test_products = self.env['product.template'].create(products)
        
        # Measure query count
        initial_queries = self.cr._obj.queries
        
        # This should not generate N queries
        turnover_rates = test_products.mapped('turnover_rate')
        
        query_count = len(self.cr._obj.queries) - len(initial_queries)
        
        # Should be O(1) queries, not O(N)
        self.assertLess(query_count, 5, "Too many queries generated")
```

### Debugging and Profiling Patterns

```python
# Advanced Debugging Tools
from odoo.tools.profiler import profile
import logging

_logger = logging.getLogger(__name__)

class DebuggableModel(models.Model):
    _name = 'debuggable.model'
    
    @profile
    def performance_critical_method(self):
        """Method with performance profiling."""
        # Profile decorator will show execution time
        return self._complex_computation()
    
    def debug_sql_operations(self):
        """Debug SQL operations."""
        # Log SQL queries
        initial_count = self.env.cr.sql_log_count
        
        result = self._database_intensive_operation()
        
        query_count = self.env.cr.sql_log_count - initial_count
        _logger.info(f"Operation executed {query_count} SQL queries")
        
        if query_count > 10:
            _logger.warning("High query count detected - possible N+1 problem")
        
        return result
    
    def memory_efficient_processing(self, large_dataset):
        """Process large datasets efficiently."""
        import tracemalloc
        
        tracemalloc.start()
        
        try:
            result = self._process_dataset(large_dataset)
            
            current, peak = tracemalloc.get_traced_memory()
            _logger.info(
                f"Memory usage: current={current/1024/1024:.1f}MB, "
                f"peak={peak/1024/1024:.1f}MB"
            )
            
            return result
        finally:
            tracemalloc.stop()
```

## Framework Philosophy Patterns

### The Odoo Way vs Anti-Patterns

```python
# ✅ GOOD: Work with the framework
class OdooWayModel(models.Model):
    _name = 'odoo.way.model'
    
    # Let Odoo handle the complex stuff
    def compute_totals(self):
        # Use ORM aggregation
        return self.read_group(
            [],
            ['amount:sum'],
            ['partner_id']
        )
    
    # Respect framework patterns
    @api.model_create_multi
    def create(self, vals_list):
        # Batch creation supported
        return super().create(vals_list)

# ❌ BAD: Fight the framework  
class AntiPatternModel(models.Model):
    _name = 'anti.pattern.model'
    
    def compute_totals_wrong(self):
        # Raw SQL when ORM would work
        self.env.cr.execute("SELECT partner_id, SUM(amount) FROM my_table GROUP BY partner_id")
        return self.env.cr.dictfetchall()
    
    def create(self, vals):
        # Force single record creation (inefficient)
        return super(AntiPatternModel, self).create(vals)
```

### Scalability Considerations

```python
# Design for Scale from Day One
class ScalableModel(models.Model):
    _name = 'scalable.model'
    
    # Strategic indexing
    partner_id = fields.Many2one('res.partner', index=True)  # Frequent searches
    state = fields.Selection([...], index=True)  # Used in domains
    date_created = fields.Datetime(index=True)  # Date filtering
    
    # Don't index everything
    notes = fields.Text()  # No index - rarely searched, large content
    
    # Computed fields with careful dependencies
    @api.depends('line_ids.amount')  # Specific dependency
    def _compute_total(self):
        # Efficient aggregation
        for record in self:
            record.total = sum(record.line_ids.mapped('amount'))
    
    # Batch-aware methods
    def update_related_records(self):
        # Group operations by type
        updates_by_model = {}
        for record in self:
            model_name = record.get_related_model()
            if model_name not in updates_by_model:
                updates_by_model[model_name] = []
            updates_by_model[model_name].append(record.get_update_data())
        
        # Batch update each model type
        for model_name, updates in updates_by_model.items():
            self.env[model_name].browse([u['id'] for u in updates]).write({
                'field': [u['value'] for u in updates]
            })
```

## Decision Making Framework

### When to Use Each Approach

```python
def choose_implementation_approach(requirements):
    """Decision tree for Odoo implementations."""
    
    if requirements.get('performance_critical'):
        # Use read_group, limit queries, add strategic indexes
        return 'performance_optimized_approach'
    
    elif requirements.get('high_customization'):
        # Use mixins, inheritance, proper extension points
        return 'extensible_architecture_approach'
    
    elif requirements.get('integration_heavy'):
        # Use proper API patterns, async where needed
        return 'integration_focused_approach'
    
    elif requirements.get('user_experience_priority'):
        # Focus on view optimization, JS components
        return 'ux_optimized_approach'
    
    else:
        # Follow standard Odoo patterns
        return 'standard_odoo_approach'

# Implementation patterns for each approach
IMPLEMENTATION_PATTERNS = {
    'performance_optimized_approach': {
        'use_read_group': True,
        'strategic_indexing': True,
        'batch_operations': True,
        'minimize_computed_fields': True
    },
    'extensible_architecture_approach': {
        'use_mixins': True,
        'proper_inheritance': True,
        'hook_methods': True,
        'event_system': True
    },
    # ... other patterns
}
```
