# Service Mocking Reference

Comprehensive guide for mocking Odoo services in Hoot tests. This reference is not loaded into agent contexts to preserve tokens.

## Core Services

### ORM Service

Complete mock implementation with all common methods:

```javascript
const mockOrm = {
    // Read records
    read: async (model, ids, fields = []) => {
        if (model === "product.template") {
            return [{
                id: ids[0],
                name: "Test Product",
                list_price: 100,
                standard_price: 50,
                categ_id: [1, "Category"],
                type: "consu"
            }]
        }
        if (model === "res.partner") {
            return [{
                id: ids[0],
                name: "Test Partner",
                email: "test@example.com",
                is_company: false
            }]
        }
        return []
    },
    
    // Search records
    search: async (model, domain = [], options = {}) => {
        const { limit = 80, offset = 0, order = "" } = options
        // Return array of IDs
        if (model === "product.template") {
            return [1, 2, 3].slice(offset, offset + limit)
        }
        return []
    },
    
    // Search and read
    searchRead: async (model, domain = [], fields = [], options = {}) => {
        const ids = await mockOrm.search(model, domain, options)
        return mockOrm.read(model, ids, fields)
    },
    
    // Write values
    write: async (model, ids, vals) => {
        // Track writes for assertions
        writeLog.push({ model, ids, vals })
        return true
    },
    
    // Create records
    create: async (model, vals) => {
        const newId = nextId++
        createLog.push({ model, id: newId, vals })
        return newId
    },
    
    // Delete records
    unlink: async (model, ids) => {
        unlinkLog.push({ model, ids })
        return true
    },
    
    // Call methods
    call: async (model, method, args = [], kwargs = {}) => {
        if (method === "name_get") {
            return args[0].map(id => [id, `Record ${id}`])
        }
        if (method === "default_get") {
            return { active: true, state: "draft" }
        }
        return true
    },
    
    // Silent mode (no loading indicator)
    silent: {
        call: async (...args) => mockOrm.call(...args)
    }
}
```

### Notification Service

```javascript
const notifications = [] // Track for assertions

const mockNotification = {
    add: (message, options = {}) => {
        const notification = {
            message,
            type: options.type || "info",
            sticky: options.sticky || false,
            className: options.className || "",
            title: options.title || ""
        }
        notifications.push(notification)
        return () => {} // Return close function
    },
    
    // For permission notifications
    requestPermission: async () => "granted"
}
```

### Action Service

```javascript
const actionHistory = []

const mockAction = {
    doAction: async (action, options = {}) => {
        actionHistory.push({ action, options })
        
        // Handle different action types
        if (typeof action === "string") {
            // Client action
            return { type: "ir.actions.client", tag: action }
        }
        
        if (action.type === "ir.actions.act_window") {
            return {
                ...action,
                id: action.id || nextActionId++
            }
        }
        
        return action
    },
    
    loadAction: async (actionId) => {
        return {
            id: actionId,
            type: "ir.actions.act_window",
            name: "Test Action",
            res_model: "product.template",
            view_mode: "tree,form"
        }
    },
    
    restore: async (actionId) => {
        return mockAction.loadAction(actionId)
    }
}
```

### Dialog Service

```javascript
const dialogs = []

const mockDialog = {
    add: (Component, props = {}) => {
        const dialog = {
            Component,
            props,
            id: nextDialogId++,
            closed: false
        }
        dialogs.push(dialog)
        
        // Return close function
        return () => {
            dialog.closed = true
        }
    },
    
    // Common dialog shortcuts
    alert: async (message, options = {}) => {
        mockDialog.add("AlertDialog", { message, ...options })
        return true
    },
    
    confirm: async (message, options = {}) => {
        mockDialog.add("ConfirmDialog", { message, ...options })
        return options.mockConfirm !== undefined ? options.mockConfirm : true
    }
}
```

### RPC Service

```javascript
const mockRpc = {
    query: async ({ route, params = {} }) => {
        rpcLog.push({ route, params })
        
        // Route handlers
        if (route === "/web/dataset/call_kw") {
            const { model, method, args, kwargs } = params
            return mockOrm.call(model, method, args, kwargs)
        }
        
        if (route === "/web/session/get_session_info") {
            return {
                uid: 2,
                is_admin: false,
                is_system: false,
                user_context: { lang: "en_US", tz: "UTC" },
                db: "test_db",
                server_version: "18.0"
            }
        }
        
        return {}
    }
}
```

### User Service

```javascript
const mockUser = {
    userId: 2,
    name: "Test User",
    isAdmin: false,
    isSystem: false,
    partnerId: 3,
    
    hasGroup: async (group) => {
        const userGroups = [
            "base.group_user",
            "stock.group_stock_user"
        ]
        return userGroups.includes(group)
    },
    
    updateContext: (context) => {
        Object.assign(mockUser.context, context)
    },
    
    context: {
        lang: "en_US",
        tz: "UTC",
        uid: 2
    }
}
```

### Company Service

```javascript
const mockCompany = {
    currentCompany: {
        id: 1,
        name: "Test Company",
        currency_id: [1, "USD"],
        partner_id: [1, "Test Company"]
    },
    
    allowedCompanies: [
        { id: 1, name: "Test Company" },
        { id: 2, name: "Other Company" }
    ],
    
    setCompanies: (companyIds) => {
        // Handle company switch
        if (companyIds[0] !== mockCompany.currentCompany.id) {
            mockCompany.currentCompany = mockCompany.allowedCompanies
                .find(c => c.id === companyIds[0])
        }
    }
}
```

## Specialized Services

### Field Service (for computed fields)

```javascript
const mockField = {
    loadFields: async (model, options = {}) => {
        const fields = {
            "product.template": {
                name: { type: "char", string: "Name", required: true },
                list_price: { type: "float", string: "Sales Price" },
                standard_price: { type: "float", string: "Cost" },
                categ_id: { 
                    type: "many2one", 
                    relation: "product.category",
                    string: "Category"
                },
                tax_ids: {
                    type: "many2many",
                    relation: "account.tax",
                    string: "Taxes"
                }
            }
        }
        return fields[model] || {}
    },
    
    loadViews: async (model, views, options = {}) => {
        return {
            fields: await mockField.loadFields(model),
            views: {
                form: {
                    arch: '<form><field name="name"/></form>'
                },
                list: {
                    arch: '<tree><field name="name"/></tree>'
                }
            }
        }
    }
}
```

### Menu Service

```javascript
const mockMenu = {
    getApps: async () => [
        {
            actionID: 1,
            id: 1,
            name: "Inventory",
            xmlid: "stock.menu_stock_root",
            appID: 1
        },
        {
            actionID: 2,
            id: 2,
            name: "Sales",
            xmlid: "sale.sale_menu_root",
            appID: 2
        }
    ],
    
    getMenuAsTree: async (menuId) => {
        return {
            id: menuId,
            name: "Test Menu",
            children: [
                { id: 10, name: "Submenu 1", children: [] },
                { id: 11, name: "Submenu 2", children: [] }
            ]
        }
    }
}
```

### Effect Service (for animations)

```javascript
const mockEffect = {
    add: (options = {}) => {
        const effect = {
            type: options.type || "rainbow_man",
            message: options.message || "",
            fadeout: options.fadeout || "slow"
        }
        effects.push(effect)
        
        // Auto-remove after timeout
        setTimeout(() => {
            const index = effects.indexOf(effect)
            if (index > -1) effects.splice(index, 1)
        }, 2000)
    }
}
```

## Complete Mock Environment Setup

```javascript
import { makeMockEnv } from "@web/../tests/web_test_helpers"

function createMockEnvironment() {
    const logs = {
        write: [],
        create: [],
        unlink: [],
        rpc: [],
        actions: [],
        notifications: [],
        dialogs: []
    }
    
    const serviceRegistry = {
        orm: createMockOrm(logs),
        notification: createMockNotification(logs),
        action: createMockAction(logs),
        dialog: createMockDialog(logs),
        rpc: createMockRpc(logs),
        user: mockUser,
        company: mockCompany,
        field: mockField,
        menu: mockMenu,
        effect: mockEffect,
        
        // Additional services
        router: {
            current: { hash: "", search: "", pathname: "/" },
            pushState: (hash) => {}
        },
        
        localization: {
            dateFormat: "MM/dd/yyyy",
            timeFormat: "HH:mm:ss",
            dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
            decimalPoint: ".",
            thousandsSep: ","
        },
        
        cookie: {
            get: (name) => null,
            set: (name, value) => {}
        },
        
        title: {
            setParts: (parts) => {}
        }
    }
    
    return {
        env: makeMockEnv({ serviceRegistry }),
        logs,
        serviceRegistry
    }
}

// Usage in test
test("complex component test", async () => {
    const { env, logs } = createMockEnvironment()
    
    await mountComponent(MyComponent, { env })
    
    // Perform actions...
    
    // Assert on logs
    expect(logs.write).toHaveLength(1)
    expect(logs.notifications).toContainEqual({
        message: "Saved successfully",
        type: "success"
    })
})
```

## Testing Patterns

### Pattern: Mock Only What You Need

```javascript
// ❌ Over-mocking
const serviceRegistry = {
    orm: fullOrmMock,
    notification: fullNotificationMock,
    action: fullActionMock,
    // ... 20 more services
}

// ✅ Mock only used services
const serviceRegistry = {
    orm: {
        write: async () => true
    },
    notification: {
        add: (msg) => expect(msg).toBe("Saved!")
    }
}
```

### Pattern: Track Service Calls

```javascript
test("tracks service interactions", async () => {
    const ormCalls = []
    
    const serviceRegistry = {
        orm: {
            write: async (...args) => {
                ormCalls.push({ method: "write", args })
                return true
            }
        }
    }
    
    const env = makeMockEnv({ serviceRegistry })
    await mountComponent(MyComponent, { env })
    
    // Trigger save
    await click(".save-btn")
    
    // Verify calls
    expect(ormCalls).toHaveLength(1)
    expect(ormCalls[0]).toEqual({
        method: "write",
        args: ["product.template", [1], { name: "New Name" }]
    })
})
```

### Pattern: Conditional Responses

```javascript
const mockOrm = {
    read: async (model, ids) => {
        // Different responses based on input
        if (model === "product.template" && ids.includes(1)) {
            return [{ id: 1, name: "Special Product" }]
        }
        if (model === "product.template") {
            return ids.map(id => ({ id, name: `Product ${id}` }))
        }
        throw new Error(`Unknown model: ${model}`)
    }
}
```

### Pattern: Async Behavior

```javascript
const mockOrm = {
    write: async (model, ids, vals) => {
        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 100))
        
        // Simulate random failure
        if (Math.random() < 0.1) {
            throw new Error("Network error")
        }
        
        return true
    }
}
```

### Pattern: Stateful Mocks

```javascript
function createStatefulOrm() {
    const records = new Map()
    let nextId = 1
    
    return {
        create: async (model, vals) => {
            const id = nextId++
            records.set(`${model}-${id}`, { id, ...vals })
            return id
        },
        
        read: async (model, ids) => {
            return ids.map(id => 
                records.get(`${model}-${id}`) || null
            ).filter(Boolean)
        },
        
        write: async (model, ids, vals) => {
            ids.forEach(id => {
                const key = `${model}-${id}`
                const record = records.get(key)
                if (record) {
                    Object.assign(record, vals)
                }
            })
            return true
        }
    }
}
```

## Common Assertions

```javascript
// Service was called
expect(logs.notifications).toContainEqual({
    message: "Success",
    type: "success"
})

// Service was called with specific args
expect(logs.orm.write).toContainEqual({
    model: "product.template",
    ids: [1],
    vals: { price: 150 }
})

// Service was not called
expect(logs.actions).toHaveLength(0)

// Service was called in order
expect(logs.rpc[0].route).toBe("/web/session/get_session_info")
expect(logs.rpc[1].route).toBe("/web/dataset/call_kw")

// Error handling
await expect(async () => {
    await click(".dangerous-btn")
}).rejects.toThrow("Validation error")
```