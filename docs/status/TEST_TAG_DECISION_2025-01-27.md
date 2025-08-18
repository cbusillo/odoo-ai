# Test Tag Configuration Decision - January 27, 2025

## Decision Summary

Following Odoo Engineer's analysis, we're using the **idiomatic Odoo 18 approach** with semantic tags.

## Current Status

- **Test decorators**: `@tagged("post_install", "-at_install")` ✅ CORRECT
- **Test runner**: Mixed approach ❌ NEEDS FIX
    - Python: `--test-tags=post_install,-at_install` ✅
    - All: `--test-tags=post_install,-at_install,product_connect_tour` ❌

## The Correct Approach

Use Odoo's semantic tags that describe WHEN tests run, not WHICH module:

- `post_install` - Run after module installation
- `-at_install` - Don't run during installation
- NO module-specific tags like `product_connect`

## Why We Went Back and Forth

1. Initially tried module-specific tags (`product_connect`) - not idiomatic
2. Changed to semantic tags in test files - correct
3. Test runner wasn't updated to match - causing filtering issues

## Final Implementation

```python
# For all test types
--test-tags=post_install,-at_install

# Tests already have correct decorators
@tagged("post_install", "-at_install")
```

## Benefits

- Matches Odoo core patterns
- Works with standard tooling
- Future-proof against Odoo updates
- Clear semantics about test execution timing