Title: Owl Component Patterns

Detailed Owl.js 2.0 component patterns for Odoo 18.

## Field Widget Pattern

```javascript
import { Component } from "@odoo/owl"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"

export class ColorPickerField extends Component {
    static template = "module.ColorPickerField"
    static props = standardFieldProps

    get value() {
        return this.props.record.data[this.props.name] || "#000000"
    }

    onChange(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value })
    }
}

registry.category("fields").add("color_picker", {
    component: ColorPickerField,
    displayName: "Color Picker",
    supportedTypes: ["char"],
})
```

### Field Widget Template

```xml
<templates xml:space="preserve">
    <t t-name="module.ColorPickerField" owl="1">
        <input type="color" 
               class="o_field_color"
               t-att-value="value"
               t-att-readonly="props.readonly"
               t-on-change="onChange" />
    </t>
</templates>
```

## View Component Pattern

```javascript
import { Component } from "@odoo/owl"
import { registry } from "@web/core/registry"
import { Layout } from "@web/search/layout"
import { useService } from "@web/core/utils/hooks"
import { graphView } from "@web/views/graph/graph_view"

export class CustomGraphController extends graphView.Controller {
    setup() {
        super.setup()
        this.notification = useService("notification")
    }

    onCustomAction() {
        this.notification.add("Custom action triggered", {
            type: "success"
        })
    }
}

export const customGraphView = {
    ...graphView,
    Controller: CustomGraphController,
}

registry.category("views").add("custom_graph", customGraphView)
```

## Action Dialog Pattern

```javascript
import { Component } from "@odoo/owl"
import { Dialog } from "@web/core/dialog/dialog"
import { useService } from "@web/core/utils/hooks"

export class ImportDialog extends Component {
    static template = "module.ImportDialog"
    static components = { Dialog }
    static props = {
        close: Function,
        title: { type: String, optional: true },
    }

    setup() {
        this.orm = useService("orm")
        this.notification = useService("notification")
    }

    async onImport() {
        try {
            await this.orm.call("product.import.wizard", "import_products", [])
            this.notification.add("Import successful", { type: "success" })
            this.props.close()
        } catch (error) {
            this.notification.add("Import failed", { type: "danger" })
        }
    }
}
```

## Service Hook Pattern

```javascript
import { Component, onWillStart } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"

export class UserDashboard extends Component {
    static template = "module.UserDashboard"
    
    setup() {
        this.user = useService("user")
        this.company = useService("company")
        this.orm = useService("orm")
        
        onWillStart(async () => {
            this.dashboardData = await this.loadDashboardData()
        })
    }
    
    async loadDashboardData() {
        const userId = this.user.userId
        return await this.orm.call("res.users", "get_dashboard_data", [userId])
    }
}
```

## Reactive State Pattern

```javascript
import { Component, useState, reactive } from "@odoo/owl"

export class TodoList extends Component {
    static template = "module.TodoList"
    
    setup() {
        this.state = useState({
            todos: [],
            filter: "all",
        })
        
        this.stats = reactive({
            get total() {
                return this.todos.length
            },
            get completed() {
                return this.todos.filter(t => t.done).length
            }
        })
    }
    
    addTodo(text) {
        this.state.todos.push({
            id: Date.now(),
            text,
            done: false,
        })
    }
    
    get filteredTodos() {
        if (this.state.filter === "active") {
            return this.state.todos.filter(t => !t.done)
        }
        return this.state.todos
    }
}
```

## Sub-component Pattern

```javascript
// Parent component
export class ProductList extends Component {
    static template = "module.ProductList"
    static components = { ProductCard }
    
    setup() {
        this.state = useState({
            products: [],
            loading: true,
        })
    }
}

// Child component
export class ProductCard extends Component {
    static template = "module.ProductCard"
    static props = {
        product: Object,
        onSelect: { type: Function, optional: true },
    }
    
    onClick() {
        if (this.props.onSelect) {
            this.props.onSelect(this.props.product)
        }
    }
}
```

## Effect Hook Pattern

```javascript
import { Component, onMounted, onWillUnmount, useEffect } from "@odoo/owl"

export class AutoSaveForm extends Component {
    static template = "module.AutoSaveForm"
    
    setup() {
        this.state = useState({ content: "" })
        let saveTimeout
        
        // Save on content change
        useEffect(() => {
            clearTimeout(saveTimeout)
            saveTimeout = setTimeout(() => {
                this.autoSave()
            }, 1000)
        }, () => [this.state.content])
        
        // Cleanup on unmount
        onWillUnmount(() => {
            clearTimeout(saveTimeout)
        })
    }
    
    async autoSave() {
        await this.orm.write("my.model", [this.recordId], {
            content: this.state.content
        })
    }
}
```
