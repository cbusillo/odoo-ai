---
title: Owl Troubleshooting
---


Common frontend issues and solutions.

## Asset Loading Issues

### Problem: Changes not appearing

```bash
# Solution 1: Clear browser cache
Cmd+Shift+R (Mac) or Ctrl+Shift+R (PC)

# Solution 2: Update module
docker exec ${ODOO_PROJECT_NAME}-script-runner-1 /odoo/odoo-bin \
  -u product_connect --stop-after-init

# Solution 3: Restart containers
docker restart ${ODOO_PROJECT_NAME}-web-1
```

### Problem: Asset not found

```python
# Check manifest
'web.assets_backend': [
    'module/static/src/components/**/*.js',  # Glob pattern
    'module/static/src/components/**/*.xml',
]

# Verify file exists
ls addons/module/static/src/components/
```

## Template Errors

### Problem: Template not found

```javascript
// ❌ Wrong
static template = "MyComponent"  // Missing module prefix

// ✅ Correct
static template = "module.MyComponent"
```

### Problem: XML parsing error

```xml
<!-- ❌ Wrong - missing xml:space -->
<templates>
    <t t-name="module.Component">
        <div>Content</div>
    </t>
</templates>

<!-- ✅ Correct -->
<templates xml:space="preserve">
    <t t-name="module.Component">
        <div>Content</div>
    </t>
</templates>
```

### Problem: Self-closing tags

```xml
<!-- ❌ Wrong - unclosed tag -->
<input type="text" value="test">

<!-- ✅ Correct - self-closing -->
<input type="text" value="test" />
```

## Props Validation Errors

### Problem: Invalid prop type

```javascript
// Component expects
static props = {
    record: Object,
    readonly: Boolean,
}

// ❌ Wrong usage
<MyComponent record="not-object" readonly="true" />

// ✅ Correct usage  
<MyComponent record="record" readonly="true" />
```

### Problem: Missing required prop

```javascript
// If you see: "Missing required prop: record"
// Check parent component passes all required props
```

## Service Errors

### Problem: Service not found

```javascript
// Error: Service "product" is not available
// Solution: Register the service

import { registry } from "@web/core/registry"

registry.category("services").add("product", productService)
```

### Problem: Service dependency issue

```javascript
// Ensure dependencies are listed
export const myService = {
    dependencies: ["orm", "notification"],  // Required!
    start(env, { orm, notification }) {
        // Service implementation
    }
}
```

## State Management Issues

### Problem: State not updating

```javascript
// ❌ Wrong - mutating state
this.state.items.push(newItem)  // Won't trigger re-render

// ✅ Correct - replace array
this.state.items = [...this.state.items, newItem]
```

### Problem: Lost reactivity

```javascript
// ❌ Wrong - non-reactive assignment
setup() {
    this.data = { count: 0 }  // Not reactive!
}

// ✅ Correct - use useState
setup() {
    this.state = useState({ count: 0 })  // Reactive!
}
```

## Event Handling Issues

### Problem: Event not firing

```xml
<!-- ❌ Wrong - missing t- prefix -->
<button onclick="handleClick">Click</button>

<!-- ✅ Correct -->
<button t-on-click="handleClick">Click</button>
```

### Problem: Wrong context in handler

```javascript
// ❌ Wrong - loses 'this' context
<button t-on-click="this.handleClick">

// ✅ Correct - bound automatically
<button t-on-click="handleClick">

// ✅ Or inline arrow function
<button t-on-click="() => this.handleClick()">
```

## Debugging Tips

### Browser Console

```javascript
// Access Owl debug info
window.odoo.__WOWL_DEBUG__.root  // Root component
window.odoo.__WOWL_DEBUG__.apps  // All apps

// Check component state
const comp = window.odoo.__WOWL_DEBUG__.root
console.log(comp.state)
```

### Chrome DevTools

```javascript
// Use Owl DevTools extension
// Shows component tree, props, state

// Or manual debugging
debugger  // Add breakpoint in component
```

### Console Errors

```javascript
// Check browser console
Collect browser console messages

// Common errors:
// - "Cannot read property of undefined" - Check data availability
// - "Template not found" - Check template name and registration
// - "Invalid props" - Check prop types match
```

## Performance Issues

### Problem: Slow rendering

```javascript
// ❌ Heavy computation in template
<t t-foreach="computeExpensiveList()" t-as="item">

// ✅ Compute once in setup
setup() {
    this.expensiveList = computeExpensiveList()
}
```

### Problem: Too many re-renders

```javascript
// ❌ Creating new objects in render
<Child t-props="{ data: { ...item } }" />

// ✅ Stable references
setup() {
    this.childProps = { data: item }
}
```

## Common Mistakes

### Forgetting owl="1" attribute

```xml
<!-- ❌ Component won't work -->
<t t-name="module.Component">

<!-- ✅ Correct for Owl components -->
<t t-name="module.Component" owl="1">
```

### Using jQuery

```javascript
// ❌ jQuery doesn't exist
$('.my-element').hide()

// ✅ Use native DOM
document.querySelector('.my-element').style.display = 'none'
```

### Wrong imports

```javascript
// ❌ Old pattern
const { Component } = require('web.core')

// ✅ Modern imports
import { Component } from "@odoo/owl"
```
