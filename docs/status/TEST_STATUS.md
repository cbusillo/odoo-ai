# 🗂️ Current Test Infrastructure Status

**LAST UPDATED - September 9, 2025:**

## Test Database Strategy (IMPLEMENTED)

- **Unit Tests**: Use blank database (`${ODOO_DB_NAME}_test_unit`) - Fast, isolated testing
- **Integration Tests**: Use production clone (`${ODOO_DB_NAME}_test_integration`) - Real data scenarios
- **Tour Tests**: Use production clone (`${ODOO_DB_NAME}_test_tour`) - Real UI workflows

## Test Results Achieved

- ✅ **Unit Tests**: 100% passing (130/130 tests)
- ✅ **Integration Tests**: 100% passing (188/188 tests) - All tests fixed!
- 🔴 **Tour Tests**: Test discovery FIXED, Chrome launches, but authentication fails

## Key Infrastructure Fixes Made

1. **Database Lock Issue Resolved**: Fixed PostgreSQL connection cleanup in `tools/test_commands.py`
2. **Production Clone Function**: Added `clone_production_database()` for real data testing
3. **Tour Test Filestore Fix**: Implemented symlink approach to share production assets without 70GB copying
4. **Shopify Sync Context**: Fixed async threading issues in test environment
5. **Test Categorization**: Rationalized JS tests — pure unit logic stays in Hoot; integration-ish JS tests replaced by
   Tours
6. **Tour Test Discovery Fixed**: Corrected test tags from `module/tests` to `post_install,-at_install`
7. **JavaScript Module Loading**: Resolved with shared test helper bundle configuration

## Critical Files Modified

- **`tools/test_commands.py`**: Production clone database strategy, robust cleanup, filestore symlink creation
- **`addons/product_connect/models/shopify_sync.py`**: Added `skip_shopify_sync` context check
- **`addons/product_connect/tests/fixtures/base.py`**: Fixed test context, SKU sequences
- **Test categorization**: JS tests moved to tour directory with proper inheritance

## Remaining Priority Work

1. **Motor Happy-Path Tour**: Expand to cover create → tests/missing parts → generate/enable parts → (mocked) export
   checks
2. **Docs**: Keep asset bundle guidance and JS vs Tour policy aligned (TESTING.md, agents/owl.md) — updated in this pass
3. **Performance Optimization**: Address N+1 queries identified by Flash agent

## Performance Improvements

- **Integration tests**: 39.48s (production clone) vs 80s (blank database)
- **Database operations**: Robust connection handling, no more timeouts
- **Test reliability**: 100% completion rate vs previous hanging issues

**Next Session Goals**: Fix tour test authentication issue (tests run but can't log in), address priority code quality
issues.

---
[← Back to Main Guide](/CLAUDE.md) | [Test Decision Log](TEST_TAG_DECISION_2025-01-27.md)
