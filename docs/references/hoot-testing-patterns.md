# Hoot Testing Patterns Reference

This document contains comprehensive patterns for writing Hoot tests in Odoo 18. It's designed as a reference guide, not loaded into agent contexts to preserve tokens.

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Component Testing](#component-testing)
3. [Service Mocking](#service-mocking)
4. [View Testing](#view-testing)
5. [Async Patterns](#async-patterns)
6. [Common Gotchas](#common-gotchas)

## Core Concepts

### Test Structure

```javascript
import { test, expect } from "@odoo/hoot"

test("description of what we're testing", async () => {
    // Setup
    // Action
    // Assertion
})
```

### Test Lifecycle

1. **Setup**: Mount components, prepare mocks
2. **Action**: Interact with component
3. **Assertion**: Verify expected outcomes
4. **Cleanup**: Automatic in Hoot

## Component Testing

### Basic Component Test

```javascript
import { test, expect } from "@odoo/hoot"
import { Component, xml, useState } from "@odoo/owl"
import { mountComponent, makeFakeEnv } from "@web/../tests/web_test_helpers"
import { click, edit } from "@odoo/hoot-dom"

test("component state management", async () => {
    class Counter extends Component {
        static template = xml`
            <div>
                <span class="count" t-esc="state.count"/>
                <button t-on-click="increment">+</button>
            </div>
        `
        setup() {
            this.state = useState({ count: 0 })
        }
        increment() {
            this.state.count++
        }
    }
    
    const comp = await mountComponent(Counter, {
        env: makeFakeEnv()
    })
    
    expect(".count").toHaveText("0")
    await click("button")
    expect(".count").toHaveText("1")
})
```

### Testing Props

```javascript
test("component with props", async () => {
    class Greeting extends Component {
        static template = xml`<h1 t-esc="props.message"/>`
        static props = {
            message: { type: String },
            optional: { type: String, optional: true }
        }
    }
    
    await mountComponent(Greeting, {
        props: { message: "Hello World" },
        env: makeFakeEnv()
    })
    
    expect("h1").toHaveText("Hello World")
})
```

### Testing Component Events

```javascript
test("component event handling", async () => {
    let eventData = null
    
    class Child extends Component {
        static template = xml`
            <button t-on-click="onClick">Click me</button>
        `
        static props = ["onCustomEvent"]
        
        onClick() {
            this.props.onCustomEvent({ value: 42 })
        }
    }
    
    class Parent extends Component {
        static template = xml`
            <Child onCustomEvent.bind="handleEvent"/>
        `
        static components = { Child }
        
        handleEvent(data) {
            eventData = data
        }
    }
    
    await mountComponent(Parent, { env: makeFakeEnv() })
    await click("button")
    
    expect(eventData).toEqual({ value: 42 })
})
```

## Service Mocking

### Complete Service Mock Setup

```javascript
import { defineParams, makeMockEnv } from "@web/../tests/web_test_helpers"

test("component with multiple services", async () => {
    const serviceRegistry = {
        orm: {
            read: async (model, ids, fields) => {
                if (model === "product.template") {
                    return [{ id: 1, name: "Product", price: 100 }]
                }
                return []
            },
            write: async (model, ids, vals) => {
                expect(model).toBe("product.template")
                expect(ids).toEqual([1])
                expect(vals).toHaveProperty("price")
                return true
            },
            create: async (model, vals) => {
                return 2 // new record ID
            },
            unlink: async (model, ids) => {
                return true
            }
        },
        notification: {
            add: (message, options = {}) => {
                // Track notifications for assertions
                notifications.push({ message, ...options })
            }
        },
        action: {
            doAction: async (action) => {
                lastAction = action
                return true
            }
        },
        dialog: {
            add: (Component, props) => {
                dialogOpened = { Component, props }
            }
        },
        user: {
            userId: 2,
            name: "Test User",
            isAdmin: false
        },
        company: {
            currentCompany: { id: 1, name: "Test Company" }
        }
    }
    
    const env = await makeMockEnv({ serviceRegistry })
    
    // Mount component with mocked services
    await mountComponent(MyComponent, { env })
})
```

### RPC Mocking

```javascript
test("component with RPC calls", async () => {
    const rpcCalls = []
    
    defineParams({
        mockRPC(route, args) {
            rpcCalls.push({ route, args })
            
            if (route === "/web/dataset/call_kw/product.template/search_read") {
                return {
                    records: [{ id: 1, name: "Product 1" }],
                    length: 1
                }
            }
            
            if (args.method === "create") {
                return 42 // new ID
            }
            
            return true
        }
    })
    
    // Component will use mocked RPC
    await mountComponent(MyComponent, { env: makeFakeEnv() })
    
    // Verify RPC calls
    expect(rpcCalls).toHaveLength(1)
    expect(rpcCalls[0].route).toContain("search_read")
})
```

## View Testing

### Testing Form Views

```javascript
import { makeView, setupViewRegistries } from "@web/../tests/views/view_test_helpers"

test("form view with custom widget", async () => {
    setupViewRegistries()
    
    const serverData = {
        models: {
            "product.template": {
                fields: {
                    name: { type: "char", string: "Name" },
                    price: { type: "float", string: "Price" },
                    color: { type: "char", string: "Color" }
                },
                records: [{
                    id: 1,
                    name: "Product 1",
                    price: 100,
                    color: "#ff0000"
                }]
            }
        }
    }
    
    await makeView({
        type: "form",
        resModel: "product.template",
        serverData,
        arch: `
            <form>
                <field name="name"/>
                <field name="price" widget="monetary"/>
                <field name="color" widget="color_picker"/>
            </form>
        `,
        resId: 1
    })
    
    expect(".o_field_widget[name='name'] input").toHaveValue("Product 1")
    expect(".o_field_widget[name='price']").toHaveText("100.00")
})
```

### Testing List Views

```javascript
test("list view interactions", async () => {
    await makeView({
        type: "list",
        resModel: "product.template",
        serverData: {
            models: {
                "product.template": {
                    fields: {
                        name: { type: "char" },
                        active: { type: "boolean" }
                    },
                    records: [
                        { id: 1, name: "Product 1", active: true },
                        { id: 2, name: "Product 2", active: false }
                    ]
                }
            }
        },
        arch: `
            <list>
                <field name="name"/>
                <field name="active" widget="boolean_toggle"/>
            </list>
        `
    })
    
    expect(".o_data_row").toHaveCount(2)
    
    // Click boolean toggle
    await click(".o_data_row:nth-child(2) .o_boolean_toggle")
    
    // Verify change
    expect(".o_data_row:nth-child(2) .o_boolean_toggle input").toBeChecked()
})
```

## Async Patterns

### Waiting Strategies

```javascript
import { animationFrame, microTick, runAllTimers } from "@odoo/hoot-mock"

test("async component behavior", async () => {
    class AsyncComponent extends Component {
        static template = xml`
            <div>
                <t t-if="state.loading">Loading...</t>
                <t t-else="">
                    <span class="content" t-esc="state.data"/>
                </t>
            </div>
        `
        
        setup() {
            this.state = useState({ loading: true, data: null })
            onMounted(() => this.loadData())
        }
        
        async loadData() {
            // Simulate async operation
            await new Promise(resolve => setTimeout(resolve, 1000))
            this.state.loading = false
            this.state.data = "Loaded!"
        }
    }
    
    await mountComponent(AsyncComponent, { env: makeFakeEnv() })
    
    // Initially loading
    expect(".content").toHaveCount(0)
    expect(":contains(Loading...)").toHaveCount(1)
    
    // Fast-forward timers
    await runAllTimers()
    await microTick() // Let state update propagate
    
    // Now loaded
    expect(".content").toHaveText("Loaded!")
})
```

### Debounced Actions

```javascript
test("debounced search", async () => {
    let searchCount = 0
    
    class SearchComponent extends Component {
        static template = xml`
            <input t-model="state.query" t-on-input="onInput"/>
        `
        
        setup() {
            this.state = useState({ query: "" })
            this.debouncedSearch = debounce(this.search.bind(this), 300)
        }
        
        onInput() {
            this.debouncedSearch()
        }
        
        search() {
            searchCount++
        }
    }
    
    await mountComponent(SearchComponent, { env: makeFakeEnv() })
    
    // Type multiple characters quickly
    await edit("input", "a")
    await edit("input", "ab")
    await edit("input", "abc")
    
    // No searches yet (debounced)
    expect(searchCount).toBe(0)
    
    // Fast-forward past debounce delay
    await runAllTimers()
    
    // Only one search executed
    expect(searchCount).toBe(1)
})
```

## Common Gotchas

### 1. Environment Setup

```javascript
// ❌ WRONG - Missing environment
await mountComponent(MyComponent)

// ✅ CORRECT - Always provide environment
await mountComponent(MyComponent, { env: makeFakeEnv() })
```

### 2. Async Operations

```javascript
// ❌ WRONG - Not waiting for state updates
comp.state.value = "new"
expect(".display").toHaveText("new") // Might fail!

// ✅ CORRECT - Wait for render
comp.state.value = "new"
await microTick()
expect(".display").toHaveText("new")
```

### 3. Service Mocking

```javascript
// ❌ WRONG - Incomplete mock
const serviceRegistry = {
    orm: {
        read: async () => []
        // Missing other methods!
    }
}

// ✅ CORRECT - Mock all used methods
const serviceRegistry = {
    orm: {
        read: async () => [],
        write: async () => true,
        create: async () => 1,
        unlink: async () => true
    }
}
```

### 4. DOM Interaction

```javascript
// ❌ WRONG - Using vanilla JS
document.querySelector("button").click()
input.value = "text"

// ✅ CORRECT - Using Hoot helpers
await click("button")
await edit("input", "text")
```

### 5. Component Cleanup

```javascript
// ❌ WRONG - Manual cleanup needed in some cases
const comp = await mountComponent(MyComponent, { env })
// ... tests ...
// Forgot to clean up!

// ✅ CORRECT - Hoot handles cleanup automatically
const comp = await mountComponent(MyComponent, { env })
// ... tests ...
// No manual cleanup needed
```

### 6. Selector Specificity

```javascript
// ❌ WRONG - jQuery-style selectors
expect("button:visible").toHaveCount(1)
expect("div:contains('text')").toExist()

// ✅ CORRECT - Standard CSS selectors
expect("button:not(.d-none)").toHaveCount(1)
expect("div").toHaveText("text")
```

## Advanced Patterns

### Testing Reactivity

```javascript
test("reactive state updates", async () => {
    const sharedState = reactive({ count: 0 })
    
    class Component1 extends Component {
        static template = xml`<div class="comp1" t-esc="state.count"/>`
        setup() {
            this.state = sharedState
        }
    }
    
    class Component2 extends Component {
        static template = xml`
            <div>
                <span class="comp2" t-esc="state.count"/>
                <button t-on-click="increment">+</button>
            </div>
        `
        setup() {
            this.state = sharedState
        }
        increment() {
            this.state.count++
        }
    }
    
    const env = makeFakeEnv()
    await mountComponent(Component1, { env })
    await mountComponent(Component2, { env })
    
    expect(".comp1").toHaveText("0")
    expect(".comp2").toHaveText("0")
    
    await click("button")
    await microTick()
    
    // Both components updated
    expect(".comp1").toHaveText("1")
    expect(".comp2").toHaveText("1")
})
```

### Testing Error Boundaries

```javascript
test("error handling", async () => {
    let errorCaught = null
    
    class ErrorBoundary extends Component {
        static template = xml`
            <div>
                <t t-if="state.hasError">
                    <div class="error">Error: <t t-esc="state.error"/></div>
                </t>
                <t t-else="">
                    <t t-slot="default"/>
                </t>
            </div>
        `
        
        setup() {
            this.state = useState({ hasError: false, error: null })
            onError((error) => {
                this.state.hasError = true
                this.state.error = error.message
            })
        }
    }
    
    class BrokenComponent extends Component {
        static template = xml`<button t-on-click="crash">Crash</button>`
        crash() {
            throw new Error("Component crashed!")
        }
    }
    
    const env = makeFakeEnv()
    const boundary = await mountComponent(ErrorBoundary, { env })
    const broken = await mountComponent(BrokenComponent, { env }, boundary)
    
    await click("button")
    await microTick()
    
    expect(".error").toHaveText("Error: Component crashed!")
})
```

## Best Practices

1. **Test behavior, not implementation**
   - Focus on user interactions and outcomes
   - Don't test internal component state directly

2. **Use descriptive test names**
   - "displays error when validation fails" ✅
   - "test validation" ❌

3. **Keep tests isolated**
   - Each test should be independent
   - Don't rely on test execution order

4. **Mock at the right level**
   - Mock services, not component methods
   - Keep mocks simple and focused

5. **Test edge cases**
   - Empty states
   - Error conditions
   - Loading states
   - Boundary values

6. **Use data-testid when needed**
   ```javascript
   // In component
   <button data-testid="submit-btn">Submit</button>
   
   // In test
   await click("[data-testid='submit-btn']")
   ```
