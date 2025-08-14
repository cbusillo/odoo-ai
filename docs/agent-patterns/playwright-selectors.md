# Playwright Selector Patterns

## Element Selection Strategy

Always use `browser_snapshot` first to get exact selectors:

```python
# 1. Get accessibility tree
snapshot = mcp__playwright__browser_snapshot()

# 2. Find element ref in snapshot output
# Look for: button, link, textbox, etc.

# 3. Use exact ref from snapshot
mcp__playwright__browser_click(
    element="Save button",  # Human description
    ref="button[name='action_save']"  # Exact ref from snapshot
)
```

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
```python
# Wait for specific text
mcp__playwright__browser_wait_for(text="Product saved successfully")

# Wait for element to appear
mcp__playwright__browser_wait_for(time=2)  # Simple wait

# Check if element exists in snapshot
snapshot = mcp__playwright__browser_snapshot()
# Look for element in snapshot output
```

### Handle Loading States
```python
# Wait for form to load
mcp__playwright__browser_wait_for(text="Loading...")  # Wait for loader to appear
mcp__playwright__browser_wait_for(textGone="Loading...")  # Wait for loader to disappear

# Or use time-based wait
mcp__playwright__browser_wait_for(time=3)
```

## Error Debugging

### Common Issues
1. **Element not found**: Take snapshot to see actual elements
2. **Element not clickable**: Check if modal or overlay is blocking
3. **Wrong selector**: Use browser_snapshot to get exact ref

### Debug Steps
```python
# 1. Take screenshot to see visual state
screenshot = mcp__playwright__browser_take_screenshot()

# 2. Get accessibility tree
snapshot = mcp__playwright__browser_snapshot()

# 3. Check console for JS errors
errors = mcp__playwright__browser_console_messages()

# 4. Check if element is in viewport
# Look for element in snapshot output
```