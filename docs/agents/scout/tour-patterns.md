# Scout Tour Test Patterns

Browser test patterns and tour definitions for UI testing.

## Tour Definition Pattern

```javascript
// static/tests/tours/product_workflow_tour.js
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("product_workflow_tour", {
    test: true,  // REQUIRED for test mode!
    url: "/odoo",  // Odoo 18 uses /odoo, not /web
    steps: () => [
        {
            trigger: ".o_app[data-menu-xmlid='product_connect.menu_root']",
            content: "Open Product Connect app",
            run: "click",
        },
        {
            trigger: ".o_list_button_add",
            content: "Create new product",
            run: "click",
        },
        {
            trigger: "input[name='name']",
            content: "Enter product name",
            run: "edit Test Product",
        },
        {
            trigger: "input[name='default_code']",
            content: "Enter valid SKU",
            run: "edit 12345678",
        },
        {
            trigger: ".o_form_button_save",
            content: "Save product",
            run: "click",
        },
        {
            trigger: ".o_form_saved",
            content: "Verify save complete",
        },
    ],
});
```

## Tour Runner Pattern

```python
from odoo.tests import tagged
from odoo.addons.product_connect.tests.fixtures.test_base import ProductConnectHttpCase

@tagged("post_install", "-at_install", "product_connect_tour")
class TestProductWorkflow(ProductConnectHttpCase):
    def test_product_workflow_tour(self):
        """Test creating a product through the UI."""
        self.start_tour("/odoo", "product_workflow_tour", login=self.test_user.login)
```

## Selector Best Practices

### ✅ GOOD Selectors

```javascript
// Data attributes
trigger: "[data-menu-xmlid='module.menu_id']"
trigger: ".o_field_widget[name='partner_id']"
trigger: "button[name='action_confirm']"

// Simple classes
trigger: ".o_list_button_add"
trigger: ".o_form_button_save"
trigger: ".o_form_saved"
```

### ❌ BAD Selectors (Don't Use!)

```javascript
// jQuery pseudo-selectors
trigger: "button:visible"  // NO!
trigger: "div:contains('Save')"  // NO!
trigger: ":first"  // NO!

// Complex paths
trigger: "div > span > button"  // Too fragile
```

## Common Tour Patterns

### Form Creation Tour

```javascript
steps: () => [
    {
        trigger: ".o_list_button_add",
        content: "Create new record",
        run: "click",
    },
    {
        trigger: ".o_field_widget[name='name'] input",
        content: "Fill name field",
        run: "edit My Record",
    },
    {
        trigger: ".o_field_widget[name='partner_id'] input",
        content: "Select partner",
        run: "edit Azure",
    },
    {
        trigger: ".ui-autocomplete .ui-menu-item:first",
        content: "Select from dropdown",
        run: "click",
    },
    {
        trigger: ".o_form_button_save",
        content: "Save record",
        run: "click",
    },
]
```

### List View Operations

```javascript
steps: () => [
    {
        trigger: "tr.o_data_row:first",
        content: "Click first record",
        run: "click",
    },
    {
        trigger: ".o_cp_action_menus button",
        content: "Open action menu",
        run: "click",
    },
    {
        trigger: ".o-dropdown-item:contains('Duplicate')",
        content: "Duplicate record",
        run: "click",
    },
]
```

### Testing Wizards

```javascript
steps: () => [
    {
        trigger: "button[name='action_open_wizard']",
        content: "Open wizard",
        run: "click",
    },
    {
        trigger: ".modal .o_field_widget[name='date_from'] input",
        content: "Set date",
        run: "edit 01/01/2024",
    },
    {
        trigger: ".modal button[name='action_confirm']",
        content: "Confirm wizard",
        run: "click",
    },
]
```

## Tour Debugging

### Add Debugging Steps

```javascript
{
    trigger: ".some_element",
    content: "Debug: Check element exists",
    run: () => {
        console.log("Element found:", document.querySelector(".some_element"));
    },
}
```

### Common Issues

1. **Timing Issues**: Element not ready
   - Solution: Use specific trigger that appears after action
   
2. **Wrong Selector**: Element not found
   - Solution: Use browser inspector to verify selector
   
3. **Tour Not Running**: Missing `test: true`
   - Solution: Add `test: true` to tour definition