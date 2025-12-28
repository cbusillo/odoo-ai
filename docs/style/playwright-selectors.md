Title: Playwright Selector Patterns

## Element Selection Strategy

Start with the accessibility tree to get exact selectors, then use role- and name-based queries when possible.

## Common Odoo Selectors

### Form Elements

```python
# Save button
ref="button[name='action_save']"
ref=".o_form_button_save"

# Edit button  
ref="button[name='action_edit']"
ref=".o_form_button_edit"

# Create button
ref=".o_list_button_add"

# Field inputs
ref="input[name='name']"
ref=".o_field_widget[name='partner_id'] input"
```

### Navigation

```python
# App menu
ref=".o_app[data-menu-xmlid='product_connect.menu_root']"

# Breadcrumb
ref=".o_control_panel .breadcrumb-item"

# Menu items
ref="a[data-menu='123']"
```

### List View

```python
# First row
ref="tr.o_data_row:first-child"

# Specific row by text
ref="tr.o_data_row:has-text('Product Name')"

# Checkbox
ref="input[type='checkbox'].o_list_record_selector"

# Column header
ref="th[data-name='name']"
```

### Dialog/Modal

```python
# Modal dialog
ref=".modal-dialog"

# Modal buttons
ref=".modal-footer .btn-primary"
ref=".modal-footer .btn-secondary"

# Close modal
ref=".modal-header .btn-close"
```

## Best Practices

### Stable Selectors (Preferred)

```python
# Data attributes (most stable)
ref="[data-menu-xmlid='module.menu_id']"
ref="[data-field-name='partner_id']"

# Name attributes
ref="button[name='action_confirm']"
ref="input[name='default_code']"

# Odoo CSS classes
ref=".o_form_button_save"
ref=".o_field_widget[name='name']"
```

### Avoid These Selectors

```python
# Generic selectors (too fragile)
ref="button:nth-child(3)"  # ❌ Position-dependent
ref="div > span > button"  # ❌ Too specific to DOM structure

# Text-based (locale-dependent)
ref="button:has-text('Save')"  # ❌ Changes with language
```

## Dynamic Content

### Wait for Elements

Prefer explicit waits for visible text or element state; avoid fixed sleeps unless necessary.

### Handle Loading States

Use loading indicators or network idle conditions instead of arbitrary timeouts.

## Error Debugging

### Common Issues

1. **Element not found**: Take snapshot to see actual elements
2. **Element not clickable**: Check if modal or overlay is blocking
3. **Wrong selector**: Use browser_snapshot to get exact ref

### Debug Steps

Steps: capture screenshot, inspect accessibility tree, review console errors, confirm element visibility, then refine
selector.
