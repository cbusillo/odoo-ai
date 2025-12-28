---
title: Hoot Testing Patterns (Owl)
---


Comprehensive Hoot test patterns for Owl.js components.

## Basic Component Test

```javascript
import { test, expect } from "@odoo/hoot"
import { Component, xml } from "@odoo/owl"
import { mountComponent } from "@web/../tests/web_test_helpers"
import { click, edit } from "@odoo/hoot-dom"

test("basic component interaction", async () => {
    class TestComponent extends Component {
        static template = xml`
            <div class="test-component">
                <input t-model="state.value" />
                <button t-on-click="save">Save</button>
                <span class="result" t-esc="state.result" />
            </div>
        `
        setup() {
            this.state = useState({ value: "", result: "" })
        }
        save() {
            this.state.result = `Saved: ${this.state.value}`
        }
    }
    
    await mountComponent(TestComponent)
    
    await edit("input", "test value")
    await click("button")
    expect(".result").toHaveText("Saved: test value")
})
```

## Service Mocking

```javascript
import { test, expect } from "@odoo/hoot"
import { defineParams, makeMockEnv } from "@web/../tests/web_test_helpers"

test("component with mocked services", async () => {
    let notificationCalled = false
    
    const serviceRegistry = {
        orm: {
            read: async (model, ids, fields) => {
                expect(model).toBe("product.template")
                return [{ id: 1, name: "Test Product", list_price: 100 }]
            },
            write: async (model, ids, vals) => {
                expect(vals.list_price).toBe(150)
                return true
            }
        },
        notification: {
            add: (message, options) => {
                notificationCalled = true
                expect(message).toBe("Price updated!")
                expect(options.type).toBe("success")
            }
        }
    }
    
    const env = await makeMockEnv({ serviceRegistry })
    
    await mountComponent(PriceEditor, {
        props: { recordId: 1 },
        env
    })
    
    await edit(".price-input", "150")
    await click(".save-btn")
    
    expect(notificationCalled).toBe(true)
})
```

## Field Widget Testing

```javascript
import { test, expect } from "@odoo/hoot"
import { makeView, setupViewRegistries } from "@web/../tests/views/view_test_helpers"
import { click } from "@odoo/hoot-dom"

test("custom field widget", async () => {
    setupViewRegistries()
    
    await makeView({
        type: "form",
        resModel: "product.template",
        serverData: {
            models: {
                "product.template": {
                    fields: {
                        color: { type: "char", string: "Color" }
                    },
                    records: [{ id: 1, color: "#ff0000" }]
                }
            }
        },
        arch: `<form><field name="color" widget="color_picker"/></form>`,
        resId: 1,
        mockRPC(route, args) {
            if (args.method === "web_save") {
                expect(args.args[1].color).toBe("#00ff00")
                return true
            }
        }
    })
    
    await click("input[type='color']")
    // Simulate color change
    const input = document.querySelector("input[type='color']")
    input.value = "#00ff00"
    input.dispatchEvent(new Event("change"))
    
    await click(".o_form_button_save")
})
```

## Async Testing

```javascript
import { test, expect } from "@odoo/hoot"
import { animationFrame, microTick } from "@odoo/hoot-mock"

test("async component operations", async () => {
    class AsyncComponent extends Component {
        static template = xml`
            <div>
                <button t-on-click="loadData">Load</button>
                <div t-if="state.loading" class="loading">Loading...</div>
                <div t-if="state.data" class="data" t-esc="state.data" />
            </div>
        `
        setup() {
            this.state = useState({ loading: false, data: null })
        }
        async loadData() {
            this.state.loading = true
            await new Promise(resolve => setTimeout(resolve, 100))
            this.state.data = "Loaded data"
            this.state.loading = false
        }
    }
    
    await mountComponent(AsyncComponent)
    
    await click("button")
    expect(".loading").toHaveCount(1)
    
    // Wait for async operation
    await animationFrame()
    await microTick()
    
    expect(".loading").toHaveCount(0)
    expect(".data").toHaveText("Loaded data")
})
```

## Dialog Testing

```javascript
import { test, expect } from "@odoo/hoot"
import { click } from "@odoo/hoot-dom"
import { makeMockEnv } from "@web/../tests/web_test_helpers"

test("dialog interaction", async () => {
    const env = await makeMockEnv()
    
    class TestDialog extends Component {
        static template = xml`
            <Dialog title="'Test Dialog'">
                <button class="confirm-btn" t-on-click="() => props.close(true)">
                    Confirm
                </button>
            </Dialog>
        `
        static components = { Dialog }
        static props = { close: Function }
    }
    
    let dialogResult = null
    await env.services.dialog.add(TestDialog, {}, {
        onClose: (result) => { dialogResult = result }
    })
    
    expect(".modal").toHaveCount(1)
    await click(".confirm-btn")
    expect(dialogResult).toBe(true)
})
```

## Component Lifecycle Testing

```javascript
import { test, expect } from "@odoo/hoot"
import { Component, onMounted, onWillUnmount } from "@odoo/owl"

test("component lifecycle hooks", async () => {
    const events = []
    
    class LifecycleComponent extends Component {
        static template = xml`<div class="lifecycle">Content</div>`
        
        setup() {
            onMounted(() => {
                events.push("mounted")
            })
            
            onWillUnmount(() => {
                events.push("will-unmount")
            })
        }
    }
    
    const comp = await mountComponent(LifecycleComponent)
    expect(events).toEqual(["mounted"])
    
    comp.destroy()
    expect(events).toEqual(["mounted", "will-unmount"])
})
```

## Props Validation Testing

```javascript
import { test, expect } from "@odoo/hoot"

test("component props validation", async () => {
    class StrictComponent extends Component {
        static template = xml`<div>{{ props.name }}</div>`
        static props = {
            name: String,
            count: { type: Number, optional: true },
            items: { type: Array, element: String }
        }
    }
    
    // Valid props
    await mountComponent(StrictComponent, {
        props: { name: "Test", items: ["a", "b"] }
    })
    
    // Invalid props should throw in dev mode
    await expect(
        mountComponent(StrictComponent, {
            props: { name: 123, items: "not-array" }
        })
    ).rejects.toThrow()
})
```

## Event Testing

```javascript
import { test, expect } from "@odoo/hoot"
import { triggerEvent } from "@odoo/hoot-dom"

test("custom event handling", async () => {
    let eventData = null
    
    class EventComponent extends Component {
        static template = xml`
            <div t-on-custom-event="onCustom">
                <ChildComponent />
            </div>
        `
        static components = { ChildComponent }
        
        onCustom(ev) {
            eventData = ev.detail
        }
    }
    
    class ChildComponent extends Component {
        static template = xml`
            <button t-on-click="emitEvent">Emit</button>
        `
        
        emitEvent() {
            this.env.bus.trigger("custom-event", { data: "test" })
        }
    }
    
    await mountComponent(EventComponent)
    await click("button")
    
    expect(eventData).toEqual({ data: "test" })
})
```
