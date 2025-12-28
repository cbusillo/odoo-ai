Title: Service Layer Patterns (Owl)

Common service usage patterns in Owl.js components.

## Core Services

### ORM Service

```javascript
import { useService } from "@web/core/utils/hooks"

setup() {
    this.orm = useService("orm")
}

// Read records
async loadProducts() {
    const products = await this.orm.searchRead(
        "product.template",
        [["active", "=", true]],
        ["name", "list_price", "default_code"],
        { limit: 100 }
    )
}

// Create record
async createProduct(data) {
    const id = await this.orm.create("product.template", data)
    return id
}

// Update record
async updatePrice(productId, newPrice) {
    await this.orm.write("product.template", [productId], {
        list_price: newPrice
    })
}

// Call method
async syncProduct(productId) {
    const result = await this.orm.call(
        "product.template",
        "sync_to_shopify",
        [productId]
    )
}
```

### Notification Service

```javascript
setup() {
    this.notification = useService("notification")
}

// Success notification
onSuccess() {
    this.notification.add(_t("Operation successful!"), {
        type: "success",
        sticky: false,
    })
}

// Error notification
onError(error) {
    this.notification.add(error.message, {
        type: "danger",
        sticky: true,
    })
}

// Warning with action
onWarning() {
    this.notification.add(_t("Check your data"), {
        type: "warning",
        buttons: [{
            text: _t("Review"),
            click: () => this.openReview(),
        }]
    })
}
```

### Action Service

```javascript
setup() {
    this.action = useService("action")
}

// Open form view
async openProduct(productId) {
    await this.action.doAction({
        type: "ir.actions.act_window",
        res_model: "product.template",
        res_id: productId,
        views: [[false, "form"]],
        target: "current",
    })
}

// Open list view with domain
async openOrders() {
    await this.action.doAction({
        type: "ir.actions.act_window",
        res_model: "sale.order",
        views: [[false, "list"], [false, "form"]],
        domain: [["state", "=", "sale"]],
        context: { default_partner_id: this.partnerId },
    })
}

// Execute action by XML ID
async runImport() {
    await this.action.doAction("product_connect.action_import_wizard")
}
```

### Dialog Service

```javascript
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"

setup() {
    this.dialog = useService("dialog")
}

// Confirmation dialog
async confirmDelete() {
    this.dialog.add(ConfirmationDialog, {
        title: _t("Delete Product"),
        body: _t("Are you sure you want to delete this product?"),
        confirm: async () => {
            await this.deleteProduct()
        },
        confirmLabel: _t("Delete"),
        cancelLabel: _t("Cancel"),
    })
}

// Custom dialog
async openSettings() {
    this.dialog.add(SettingsDialog, {
        title: _t("Settings"),
        size: "lg",
        settings: this.currentSettings,
        onSave: (newSettings) => {
            this.updateSettings(newSettings)
        },
    })
}
```

### RPC Service

```javascript
setup() {
    this.rpc = useService("rpc")
}

// Generic RPC call
async customCall() {
    const result = await this.rpc("/product_connect/custom_endpoint", {
        product_id: this.productId,
        action: "validate",
    })
}

// Call with specific model/method
async getStats() {
    const stats = await this.rpc("/web/dataset/call_kw", {
        model: "product.template",
        method: "get_statistics",
        args: [this.productIds],
        kwargs: { include_archived: true },
    })
}
```

## Custom Service Pattern

```javascript
// Define service
export const productService = {
    dependencies: ["orm", "notification"],
    
    start(env, { orm, notification }) {
        let cache = {}
        
        return {
            async getProduct(id) {
                if (!cache[id]) {
                    cache[id] = await orm.read("product.template", [id])
                }
                return cache[id]
            },
            
            clearCache() {
                cache = {}
            },
            
            async syncProduct(id) {
                try {
                    await orm.call("product.template", "sync_to_shopify", [id])
                    notification.add(_t("Sync successful"), { type: "success" })
                } catch (error) {
                    notification.add(error.message, { type: "danger" })
                }
            }
        }
    }
}

// Register service
registry.category("services").add("product", productService)

// Use in component
setup() {
    this.productService = useService("product")
}
```

## User & Company Services

```javascript
setup() {
    this.user = useService("user")
    this.company = useService("company")
}

// User info
get userName() {
    return this.user.name
}

get isAdmin() {
    return this.user.isAdmin
}

get userContext() {
    return this.user.context
}

// Company info
get companyName() {
    return this.company.name
}

get currency() {
    return this.company.currencyId
}
```

## Effect & Reactive Services

```javascript
import { useService, useEffect } from "@web/core/utils/hooks"

setup() {
    this.router = useService("router")
    
    // React to route changes
    useEffect(() => {
        this.loadDataForRoute()
    }, () => [this.router.current.hash])
}
```

## Error Handling Pattern

```javascript
setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
}

async saveWithErrorHandling() {
    try {
        await this.orm.write(this.model, [this.recordId], this.data)
        this.notification.add(_t("Saved"), { type: "success" })
    } catch (error) {
        if (error.code === 'access_denied') {
            this.notification.add(_t("Access denied"), { type: "danger" })
        } else {
            this.notification.add(error.message || _t("Save failed"), {
                type: "danger"
            })
        }
    }
}
```
