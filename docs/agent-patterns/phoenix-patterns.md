# 🔥 Phoenix Agent - Detailed Migration Patterns

This file contains detailed migration patterns and examples extracted from the Phoenix agent documentation.

## Field Modernization Patterns

### Modern Field Naming (Odoo 18)

```python
# OLD: Always _id suffix for Many2one
carrier_id = fields.Many2one('delivery.carrier')
self.carrier_id  # Returns recordset (confusing!)

# NEW: Omit _id for recordset fields
carrier = fields.Many2one('delivery.carrier')
self.carrier  # Returns recordset (clear!)

# Only use _id for actual ID fields
carrier_id = fields.Integer()  # Stores ID number
```

### String Attribute Modernization

```python
# OLD: Explicit string attributes
name = fields.Char(string="Product Name")
description = fields.Text(string="Description")

# NEW: Omit when label matches field
name = fields.Char()  # Auto-generates "Name"
description = fields.Text()  # Auto-generates "Description"

# Only specify when different:
qty = fields.Integer(string="Quantity")
internal_notes = fields.Text(string="Internal Notes")
```

## Type Hints Migration

### Python Type Hints (Python 3.10+)

```python
# OLD: typing imports
from typing import Optional, List, Dict, Tuple, Union

def method(self, vals: Optional[Dict]) -> List[str]:
    items: List[Tuple[str, int]] = []
    data: Union[str, int] = None

# NEW: Built-in types (Python 3.10+)
def method(self, vals: dict | None) -> list[str]:
    items: list[tuple[str, int]] = []
    data: str | int = None
```

### Complex Type Migrations

```python
# OLD: Complex typing patterns
from typing import Optional, Dict, List, Callable, Any

def complex_method(
    self, 
    records: Optional[List[Dict[str, Any]]], 
    callback: Callable[[str], bool]
) -> Dict[str, List[int]]:
    pass

# NEW: Modern type hints
def complex_method(
    self,
    records: list[dict[str, any]] | None,
    callback: callable[[str], bool]
) -> dict[str, list[int]]:
    pass
```

## JavaScript/Frontend Migration Patterns

### Widget to Component Migration

```javascript
// OLD: odoo.define pattern
odoo.define('module.widget', function (require) {
    "use strict";
    
    var Widget = require('web.Widget');
    var core = require('web.core');
    var QWeb = core.qweb;
    
    var MyWidget = Widget.extend({
        template: 'MyTemplate',
        events: {
            'click .btn': '_onButtonClick'
        },
        
        start: function() {
            this._super.apply(this, arguments);
        },
        
        _onButtonClick: function(ev) {
            ev.preventDefault();
        }
    });
    
    return MyWidget;
});

// NEW: ES6 modules with Owl
import { Component } from "@odoo/owl"
import { registry } from "@web/core/registry"

export class MyComponent extends Component {
    static template = "MyTemplate"
    
    setup() {
        // Initialization code
    }
    
    onButtonClick(ev) {
        ev.preventDefault();
    }
}

registry.category("actions").add("my_component", MyComponent);
```

### jQuery to Native DOM Migration

```javascript
// OLD: jQuery patterns
$(document).ready(function() {
    $('.my-class').click(function() {
        $(this).addClass('active');
        $('#my-id').hide();
    });
    
    $.ajax({
        url: '/my/endpoint',
        type: 'POST',
        data: {value: 123}
    });
});

// NEW: Native DOM methods
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.my-class').forEach(el => {
        el.addEventListener('click', function() {
            this.classList.add('active');
            document.getElementById('my-id').style.display = 'none';
        });
    });
    
    fetch('/my/endpoint', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({value: 123})
    });
});
```

## API Decorator Migration

### Removing Deprecated Decorators

```python
# OLD: @api.multi, @api.one (deprecated)
@api.multi
def method_multi(self):
    for record in self:
        record.do_something()

@api.one
def method_one(self):
    self.do_something()

# NEW: No decorator needed (modern Odoo)
def method(self):
    for record in self:
        record.do_something()

def method_single(self):
    self.ensure_one()  # Explicit single-record check
    self.do_something()
```

### Environment Access Migration

```python
# OLD: @api.model_cr, @api.model_cr_uid
@api.model_cr
def init(self, cr):
    cr.execute("CREATE INDEX ...")

@api.model_cr_uid
def old_method(self, cr, uid, context=None):
    return self.browse(cr, uid, [], context=context)

# NEW: Regular method with env access
def init(self):
    self.env.cr.execute("CREATE INDEX ...")

def new_method(self):
    # Access everything through self.env
    return self.search([])
```

## Model Inheritance Migration

### Inheritance Pattern Updates

```python
# OLD: Mixed inheritance patterns
class ProductTemplate(models.Model):
    _name = 'product.template'  # Creating new model
    _inherit = ['mail.thread']  # Inherit functionality

class ProductVariant(models.Model):
    _inherit = 'product.template'  # Extend existing model

# NEW: Clear inheritance separation
class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Multiple inheritance

class ProductVariant(models.Model):
    _inherit = 'product.template'  # Extension only
```

## Test Migration Patterns

### Modern Testing Patterns

```python
# OLD: Threading and transaction patterns
import threading
from odoo.tests import common

class TestOld(common.TransactionCase):
    def test_with_threading(self):
        def worker():
            # Complex threading setup
            pass
        
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

# NEW: Modern test patterns
from odoo.tests import tagged, TransactionCase

@tagged('post_install', '-at_install')
class TestModern(TransactionCase):
    def test_modern_pattern(self):
        # Use registry.in_test_mode() for special test behavior
        if self.env.registry.in_test_mode():
            # Test-specific logic
            pass
```

## Systematic Migration Workflow

### Step-by-Step Migration Process

1. **Identify Patterns**: Use search tools to find old patterns
2. **Validate Current State**: Check what needs updating
3. **Find Modern Examples**: Research Odoo 18 implementations
4. **Plan Migration**: Break into manageable chunks
5. **Execute Changes**: Use bulk edit tools
6. **Test Thoroughly**: Ensure behavior remains correct

### Search Commands for Common Migrations

```python
# Find old type hints
mcp__odoo_intelligence__search_code(
    pattern="from typing import.*Optional|List|Dict",
    file_type="py"
)

# Find jQuery usage
mcp__odoo_intelligence__search_code(
    pattern="\\$\\(|jQuery\\(",
    file_type="js"
)

# Find old field patterns
mcp__odoo_intelligence__search_code(
    pattern="fields\\..*_id.*=.*fields\\.Many2one",
    file_type="py"
)

# Find deprecated decorators
mcp__odoo_intelligence__search_code(
    pattern="@api\\.(multi|one|model_cr)",
    file_type="py"
)

# Find old widget patterns
mcp__odoo_intelligence__search_code(
    pattern="Widget\\.extend|widget\\.extend",
    file_type="js"
)
```

## Complete Migration Example

### Before and After: Full Model Migration

```python
# OLD: Odoo 15/16 patterns
from typing import Optional, List, Dict
from odoo import models, fields, api


class OldPatternModel(models.Model):
    _name = 'old.model'
    
    partner_id = fields.Many2one('res.partner', string="Partner")
    supplier_id = fields.Many2one('res.partner', string="Supplier")
    active = fields.Boolean(string="Active", default=True)
    
    @api.multi
    def old_compute_method(self, vals: Optional[Dict]) -> List[str]:
        result = []
        for record in self:
            result.append(record.name)
        return result
    
    @api.model_cr
    def init(self, cr):
        cr.execute("CREATE INDEX IF NOT EXISTS idx_partner ON old_model(partner_id)")

# NEW: Odoo 18 patterns
from odoo import models, fields


class ModernPatternModel(models.Model):
    _name = 'modern.model'
    
    # No _id suffix, no redundant strings
    partner = fields.Many2one('res.partner')
    supplier = fields.Many2one('res.partner')
    active = fields.Boolean(default=True)
    
    # No @api.multi, modern type hints
    def compute_method(self, vals: dict | None) -> list[str]:
        return [record.name for record in self]
    
    # No @api.model_cr
    def init(self):
        self.env.cr.execute("CREATE INDEX IF NOT EXISTS idx_partner ON modern_model(partner_id)")
```

### JavaScript Component Migration

```javascript
// OLD: Full odoo.define widget
odoo.define('custom.product_widget', function (require) {
    "use strict";
    
    var Widget = require('web.Widget');
    var Dialog = require('web.Dialog');
    var core = require('web.core');
    var _t = core._t;
    
    var ProductWidget = Widget.extend({
        template: 'ProductTemplate',
        
        events: {
            'click .product-btn': '_onProductClick',
        },
        
        init: function(parent, options) {
            this._super.apply(this, arguments);
            this.products = options.products || [];
        },
        
        start: function() {
            var def = this._super.apply(this, arguments);
            this._renderProducts();
            return def;
        },
        
        _renderProducts: function() {
            this.$('.product-list').html('');
            // Render logic
        },
        
        _onProductClick: function(ev) {
            ev.preventDefault();
            var product_id = $(ev.currentTarget).data('product-id');
            this.trigger_up('product_selected', {product_id: product_id});
        },
    });
    
    return ProductWidget;
});

// NEW: Modern Owl component
import { Component } from "@odoo/owl"
import { Dialog } from "@web/core/dialog/dialog"
import { _t } from "@web/core/l10n/translation"

export class ProductComponent extends Component {
    static template = "ProductTemplate"
    
    setup() {
        this.products = this.props.products || [];
    }
    
    onProductClick(ev) {
        ev.preventDefault();
        const productId = ev.currentTarget.dataset.productId;
        this.env.bus.trigger('product_selected', {productId});
    }
}
```

## Migration Validation Patterns

### Ensuring Complete Migration

```python
# Validation checklist after migration
def validate_migration():
    # Check for remaining old patterns
    old_patterns = [
        "from typing import",
        "@api.multi",
        "@api.one", 
        "Widget.extend",
        "odoo.define",
        "_id = fields.Many2one"
    ]
    
    for pattern in old_patterns:
        results = mcp__odoo_intelligence__search_code(
            pattern=pattern,
            file_type="py"
        )
        if results:
            print(f"Warning: Still found {pattern} in:")
            for result in results:
                print(f"  - {result}")
```