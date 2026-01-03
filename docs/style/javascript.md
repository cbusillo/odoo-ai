---
title: JavaScript Style
---


Purpose

- Define the JS and Owl rules for Odoo 18.

When

- Any time you edit JS, Owl components, or frontend tests.

Sources of Truth

- `addons/*/static/src/` — real components, services, and patterns in this repo.
- Use existing components as the primary reference; avoid inventing new
  patterns without a real precedent.

Modules and Frameworks (Odoo 18)

- Use native ES modules with imports from `@web/...` and Odoo namespaces.
- Do not use AMD `odoo.define` modules in this project.
- Do not add `/** @odoo-module */` to new files; we ship native ESM only.
- No semicolons; prefer clean ES syntax consistent with Owl.js style.

Version Guardrails

- Owl.js 2.x patterns only (hooks, native ESM modules).
- No legacy `odoo.define` modules or AMD imports.

Libraries

- Owl.js 2.0 for components; use hooks like `useState`, `useRef`, `onMounted`.
- @odoo/hoot for JS tests.

Patterns

- Components extend Owl Component; avoid legacy Widget.
- Use ES imports; avoid RequireJS.
- Prefer JSDoc for hints when helpful; keep files small and cohesive.

Service Layer Patterns

- Keep service usage aligned with code under `addons/*/static/src/`.
- Prefer small, single-purpose services and reuse existing utilities.

Troubleshooting

- If assets fail to refresh, use container tooling to rebuild/restart; see
  `docs/tooling/docker.md`.

Formatting

- Quotes: double quotes by default; template literals for interpolation.
- Indentation: 4 spaces; no tabs.
- Trailing commas: enabled in multi-line arrays/objects/params.
- Descriptive naming: camelCase for variables/functions, PascalCase for classes/components;
  prefer intention-revealing names. If you need a comment to explain "what", rename
  or refactor instead.
- DRY: extract utilities/hooks for shared logic; avoid duplicating selectors or
  event wiring.
