Title: JavaScript Style

Modules and Frameworks (Odoo 18)

- Use native ES modules with imports from `@web/...` and Odoo namespaces.
- Do not use AMD `odoo.define` modules in this project.
- Do not add `/** @odoo-module */` to new files; we ship native ESM only.
- No semicolons; prefer clean ES syntax consistent with Owl.js style.

Libraries

- Owl.js 2.0 for components; use hooks like `useState`, `useRef`, `onMounted`.
- @odoo/hoot for JS tests.

Patterns

- Components extend Owl Component; avoid legacy Widget.
- Use ES imports; avoid RequireJS.
- Prefer JSDoc for hints when helpful; keep files small and cohesive.

Formatting

- Quotes: single quotes by default; template literals for interpolation.
- Trailing commas: enabled in multi-line arrays/objects/params.
- Descriptive naming: camelCase for variables/functions, PascalCase for classes/components; prefer intention‑revealing
  names. If you need a comment to explain “what”, rename or refactor instead.
- DRY: extract utilities/hooks for shared logic; avoid duplicating selectors or event wiring.
