# JavaScript Style Rules

JavaScript-specific coding standards for Odoo 18 development.

## Semicolons

- **No semicolons**: Omit semicolons at the end of statements
- Modern JavaScript with proper file separation doesn't require them
- Cleaner and easier to read

## Libraries and Frameworks

**Use:**

- **Owl.js 2.0**: Odoo's modern component framework
    - Use hooks: `useState`, `useRef`, `onMounted`, etc.
    - Component-based architecture
- **Odoo Web Framework** (`@web/*`): Core Odoo utilities
- **@odoo/hoot**: For JavaScript testing
- **Chart.js**: Via Odoo's asset bundle for visualizations

**Do NOT use:**

- **jQuery** (`$` or `jQuery`): Odoo 18 is jQuery-free
- **Legacy widget system**: No `widget.extend` or `include()`
- **Old translation**: Use `import { _t } from "@web/core/l10n/translation"` not global `_t`
- **RequireJS/AMD**: Use ES6 modules instead
- **odoo.define()**: Use ES6 imports/exports instead

## JavaScript Patterns

- **Module files**: Start directly with ES6 imports (no module declaration comment needed)
- **Imports**: Use ES6 imports from Odoo namespaces
  ```javascript
  import { Component } from "@odoo/owl"
  import { registry } from "@web/core/registry"
  ```
- **Components**: Extend Owl Component, not old Widget class
- **No inline scripts**: All JS should be in module files
- **Type hints**: Use JSDoc for better IDE support
  ```javascript
  /** @type {import("./model").MyModel} */
  const model = this.model
  ```

## Component Structure

**Modern Owl.js 2.0 Pattern:**

```javascript
import { Component } from "@odoo/owl";

export class CustomWidget extends Component {
    static template = "product_connect.CustomWidget";
    static props = ["*"];
    
    setup() {
        // Component setup
    }
}
```

## Tour Test Selectors

- **Simple selectors only**: No `:visible` or `:contains()` jQuery patterns
- **Use basic CSS selectors**: `.class`, `[data-attribute]`, `#id`
- **Avoid complex queries**: They fail in Odoo 18 tour tests

**Good:**

```javascript
trigger: ".o_app[data-menu-xmlid='module.menu']"
```

**Bad:**

```javascript
trigger: ".o_app:visible:contains('Menu')"  // jQuery patterns don't work
```