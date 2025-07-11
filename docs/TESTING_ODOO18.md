# Testing in Odoo 18

This guide covers modern testing patterns for Odoo 18, including the limitations of tour tests and better alternatives.

## Testing Hierarchy

### 1. Python Unit Tests (TransactionCase)

For business logic, model methods, and data integrity:

```python
from odoo.tests import TransactionCase, tagged

@tagged('post_install', '-at_install')
class TestMotorProducts(TransactionCase):
    def test_create_motor_products(self):
        """Test that motor products are created correctly"""
        motor = self.env['motor'].create({
            'serial_number': 'TEST123',
            'manufacturer': 'Mercury',
            'horsepower': 250,
            'year': 2024,
            'model': 'Verado',
        })
        motor.create_motor_products()
        
        # Verify 15 products created
        self.assertEqual(len(motor.products_not_enabled), 15)
        
        # Verify product attributes
        product = motor.products_not_enabled[0]
        self.assertEqual(product.motor_id, motor)
        self.assertTrue(product.name.startswith('Mercury'))
```

### 2. HTTP Integration Tests (HttpCase)

For workflows involving UI interaction:

```python
from odoo.tests import HttpCase, tagged

@tagged('post_install', '-at_install')
class TestShippingAnalytics(HttpCase):
    def test_shipping_dashboard_loads(self):
        """Test that shipping analytics dashboard loads without errors"""
        self.authenticate('admin', 'admin')
        
        # Navigate directly to the action
        response = self.url_open('/web#action=product_connect.action_sale_order_shipping_analytics')
        self.assertEqual(response.status_code, 200)
        
        # Or use browser automation
        self.browser_js(
            '/web',
            """
            const action = await odoo.__DEBUG__.services.action.doAction(
                'product_connect.action_sale_order_shipping_analytics'
            );
            // Return true if view loaded
            return document.querySelector('.o_pivot_table') !== null;
            """,
            login='admin'
        )
```

### 3. JavaScript Unit Tests (QUnit)

For testing Owl components and widgets:

```javascript
// static/tests/views/multigraph_view.test.js
import { click, getFixture } from "@web/../tests/helpers/utils";
import { makeView, setupViewRegistries } from "@web/../tests/views/helpers";

QUnit.module("product_connect.MultigraphView", (hooks) => {
    let serverData;
    let target;

    hooks.beforeEach(() => {
        target = getFixture();
        serverData = {
            models: {
                "product.template": {
                    fields: {
                        name: { string: "Name", type: "char" },
                        revenue_value: { string: "Revenue", type: "float" },
                        cost_value: { string: "Cost", type: "float" },
                    },
                    records: [
                        { id: 1, name: "Product 1", revenue_value: 1000, cost_value: 600 },
                        { id: 2, name: "Product 2", revenue_value: 2000, cost_value: 1200 },
                    ],
                },
            },
        };
        setupViewRegistries();
    });

    QUnit.test("multigraph view renders without errors", async (assert) => {
        await makeView({
            type: "multigraph",
            resModel: "product.template",
            serverData,
            arch: `<multigraph>
                <field name="revenue_value" type="measure"/>
                <field name="cost_value" type="measure"/>
            </multigraph>`,
        });

        assert.containsOnce(target, ".o_multigraph_renderer");
        assert.containsOnce(target, "canvas");
    });

    QUnit.test("clicking chart does not throw error", async (assert) => {
        await makeView({
            type: "multigraph",
            resModel: "product.template",
            serverData,
            arch: `<multigraph/>`,
        });

        // Click on the chart
        await click(target.querySelector("canvas"));
        
        // Verify no error dialog
        assert.containsNone(target, ".o_error_dialog");
    });
});
```

### 4. Tour Tests (Limited Use)

Best for simple smoke tests and demo scenarios:

```javascript
// static/tests/tours/basic_navigation_tour.js
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("test_basic_navigation", {
    test: true,
    steps: () => [
        {
            content: "Navigate to Inventory",
            trigger: '.o_app[data-menu-xmlid="stock.menu_stock_root"]',
            run: "click",
        },
        {
            content: "Verify Inventory loaded",
            trigger: ".o_breadcrumb:contains('Inventory')",
        },
    ],
});
```

## Tour Test Limitations in Odoo 18

### What Doesn't Work Well:

1. **Complex selectors**: `:contains()`, `:visible`, `:not()` are unreliable
2. **Dynamic content**: Lazy-loaded assets, AJAX content
3. **Error handling**: Can't properly catch and handle exceptions
4. **Promises/async**: Tour steps don't handle Promises well
5. **Complex interactions**: Multi-step workflows with conditional logic

### What Works:

1. **Simple navigation**: Basic menu clicks
2. **Static content**: Elements that are always present
3. **Linear flows**: Step A → B → C without branches
4. **Smoke tests**: "Does it load without crashing?"

## Testing Best Practices for Odoo 18

### 1. Use the Right Tool for the Job

- **Model logic**: TransactionCase
- **API/Controllers**: HttpCase with url_open()
- **UI Components**: QUnit tests
- **Full workflows**: HttpCase with browser_js()
- **Simple navigation**: Tour tests

### 2. Mock External Services

```python
from unittest.mock import patch

class TestShopifyIntegration(TransactionCase):
    @patch('requests.post')
    def test_shopify_order_sync(self, mock_post):
        mock_post.return_value.json.return_value = {'order': {...}}
        # Test without hitting real API
```

### 3. Use Test Tags

```python
@tagged('fast')  # Quick unit tests
@tagged('slow')  # Integration tests
@tagged('external')  # Tests requiring external services
@tagged('-standard')  # Skip in CI
```

### 4. Test Data Isolation

```python
def setUp(self):
    super().setUp()
    # Create test-specific data
    self.test_tag = self.env['product.tag'].create({
        'name': 'Test Tag',
        'color': 10,  # Red for visibility
    })
```

## Modern Odoo 18 Patterns

### 1. Direct Action Testing

Instead of navigating through menus:

```python
def test_view_loads(self):
    """Test view loads without errors"""
    action = self.env['ir.actions.act_window']._for_xml_id(
        'product_connect.action_product_processing_analytics'
    )
    self.assertTrue(action['res_model'])
```

### 2. Component Testing with Mocks

```javascript
QUnit.test("motor test widget interactions", async (assert) => {
    const orm = {
        write: (model, ids, values) => {
            assert.strictEqual(model, "motor.test");
            assert.deepEqual(values, { yes_no_result: true });
            return Promise.resolve();
        },
    };
    
    await mountComponent(MotorTestWidget, {
        props: { record: mockRecord },
        env: { services: { orm } },
    });
});
```

### 3. Headless Browser Testing

```python
class TestComplexUI(HttpCase):
    def test_multigraph_interaction(self):
        """Test multigraph chart interactions"""
        result = self.browser_js(
            '/web',
            """
            // Navigate to view
            await odoo.__DEBUG__.services.action.doAction(
                'product_connect.action_product_processing_analytics'
            );
            
            // Wait for chart
            await new Promise(resolve => {
                const checkChart = setInterval(() => {
                    if (document.querySelector('.o_multigraph_renderer canvas')) {
                        clearInterval(checkChart);
                        resolve();
                    }
                }, 100);
            });
            
            // Click chart
            const canvas = document.querySelector('.o_multigraph_renderer canvas');
            canvas.click();
            
            // Check for errors
            return !document.querySelector('.o_error_dialog');
            """,
            login='admin',
            timeout=30
        )
        self.assertTrue(result)
```

## Important Clarification

**Odoo does NOT use Playwright natively!** Odoo has its own built-in browser automation:

1. **HttpCase with `browser_js()`** - Runs real Chrome/Chromium browser
2. **HttpCase with `start_tour()`** - Runs tour tests in real browser
3. **QUnit tests** - Component testing framework
4. **Hoot tests** (Odoo 17+) - Modern testing framework

The Playwright references earlier were examples of *possible* custom integrations, not standard Odoo practice.

## Recommended Test Structure

```
product_connect/
├── tests/
│   ├── test_models.py              # Unit tests for models
│   ├── test_shopify_sync.py        # Integration tests with mocks
│   ├── test_workflows.py           # HttpCase workflow tests
│   ├── test_multigraph_integration.py  # Browser automation tests
│   └── test_tours.py               # Simple tour runners
└── static/tests/
    ├── tours/
    │   └── demo_tour.js            # Demo/training tours only
    ├── views/
    │   └── multigraph_view.test.js  # QUnit view tests
    └── widgets/
        └── motor_test_widget.test.js  # QUnit widget tests
```

## Running Tests

```bash
# All tests
./tools/test_runner.py all

# Specific test types
./tools/test_runner.py python
./tools/test_runner.py js
./tools/test_runner.py tour

# With tags
./tools/test_runner.py python --test-tags fast
./tools/test_runner.py python --test-tags -slow,-external

# Specific test
./tools/test_runner.py python --test-tags TestMotorProducts.test_create_motor_products
```

## Key Takeaways

1. **Tour tests are limited** - Use them only for simple smoke tests
2. **QUnit/Hoot are better** for testing UI components and interactions
3. **HttpCase.browser_js()** is powerful for complex UI testing
4. **Mock external services** to make tests reliable and fast
5. **Use proper test structure** to organize different test types

The key insight is that Odoo has its own built-in browser automation through HttpCase - you don't need Playwright or
Selenium for most testing scenarios.