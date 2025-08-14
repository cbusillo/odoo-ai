# CSS & Styling Guidelines

CSS and styling standards for Odoo 18 Enterprise customizations.

## Framework Stack

- **Bootstrap 5.3+** - Core CSS framework
- **Owl.js 2.0** - Component styling integration
- **SCSS** - CSS preprocessing (when available)
- **Odoo Web Assets** - Asset bundling system

## File Organization

```
static/
├── src/
│   ├── css/           # Custom stylesheets
│   ├── scss/          # SCSS source files
│   └── components/    # Component-specific styles
```

## Odoo CSS Conventions

### Class Naming

```css
/* ✅ Follow Odoo conventions */
.o_product_connect_motor_card { }
.o_pc_specs_table { }

/* ❌ Generic naming */
.motor-card { }
.specs-table { }
```

### Component Integration

```css
/* ✅ Owl component styling */
.o_product_connect_component {
    /* Component root styles */
}

.o_product_connect_component .o_field_widget {
    /* Field-specific styles */
}
```

## Bootstrap Integration

```css
/* ✅ Use Bootstrap utilities */
.o_custom_section {
    @extend .card;
    @extend .mb-3;
}

/* ❌ Reinvent Bootstrap patterns */
.o_custom_section {
    border: 1px solid #dee2e6;
    border-radius: 0.375rem;
    margin-bottom: 1rem;
}
```

## Asset Management

```xml
<!-- ✅ Proper asset declaration -->
<template id="assets_backend" inherit_id="web.assets_backend">
    <xpath expr="." position="inside">
        <link rel="stylesheet" href="/product_connect/static/src/css/motor_views.css"/>
    </xpath>
</template>
```

## Performance Guidelines

- **Minimize CSS bundle size** - Only include necessary styles
- **Use CSS custom properties** - For themeable values
- **Avoid deep nesting** - Keep specificity low
- **Leverage Odoo's design system** - Don't reinvent components

## Responsive Design

```css
/* ✅ Mobile-first approach */
.o_motor_specs {
    display: block;
}

@media (min-width: 768px) {
    .o_motor_specs {
        display: flex;
    }
}
```

## Common Patterns

### List Views

```css
.o_list_view .o_motor_row {
    /* Custom list styling */
}
```

### Form Views

```css
.o_form_view .o_motor_specs_section {
    /* Form section styling */
}
```

### Kanban Views

```css
.o_kanban_view .o_motor_card {
    /* Kanban card styling */
}
```

## Need More?

- **Odoo Documentation
  **: [CSS Guidelines](https://www.odoo.com/documentation/18.0/developer/reference/frontend/assets.html)
- **Bootstrap Docs**: [Bootstrap 5.3](https://getbootstrap.com/docs/5.3/)
- **Agent Support**: Use Owl agent for CSS/styling tasks