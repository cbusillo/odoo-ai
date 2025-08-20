# NEXT_PROMPT.md

## Current State (2025-08-19 - Final Update)

### ✅ What's Working
- **Unit Tests**: 130/130 passing ✅ (with original test_runner.py from commit 48dc13f)
- **Integration Tests**: 195/195 passing ✅
- **Total Python Tests**: 325/325 passing ✅
- Critical error detection properly skips validation tests
- Secure authentication implemented for tour tests
- SKU generation using factories (no hardcoded values)
- Standardized on "integration" terminology (replaced "validation")
- GPT agent delegation pattern documented in CLAUDE.md

### ⚠️ Important Note
**DO NOT MODIFY test_runner.py tag format!** The GPT agent's attempted "fixes" broke unit tests by changing the tag format. The current format works perfectly.

### ❌ Remaining Issues

#### 1. Tour Test JavaScript Dependencies (ONLY REMAINING ISSUE)

**Error**: Tour tests fail with missing JavaScript module dependencies
```
The following modules could not be loaded because they have unmet dependencies:
['@product_connect/../tests/helpers/test_base', 
 '@product_connect/../tests/basic.test',
 '@product_connect/../tests/motor_form.test', 
 ... (13 modules total)]
```

**Files Exist**: Confirmed JavaScript test files exist in `addons/product_connect/static/tests/`
**Problem**: Asset bundling configuration in `__manifest__.py` is incorrect
**GPT Agent Attempted**: Added gevent workers for websocket support (lines 590-593 in test_runner.py)

**Fix Needed**:
- Update `__manifest__.py` assets section to properly register test files
- Unit test files (*.test.js) should be in different bundle than tour files
- Tour files are in `static/tests/tours/` directory

**To Test**: 
```bash
docker restart odoo-opw-script-runner-1  # Restart container first
python tools/test_runner.py tour
```

#### 2. Full Test Suite (`test-all`) Hanging (LOW PRIORITY)
**Issue**: `uv run test-all` times out - likely due to tour test JavaScript issues
**Workaround**: Run categories individually (unit and integration work perfectly)

## Quick Commands

```bash
# Run individual test categories (Python tests all working!)
python tools/test_runner.py unit        # ✅ 130 tests, ~3 min
python tools/test_runner.py integration # ✅ 195 tests, ~5 min
python tools/test_runner.py tour        # ❌ Fails - JS dependencies

# Alternative runners
uv run test-unit         # ✅ Works
uv run test-integration  # ✅ Works
uv run test-tour         # ❌ Fails - JS dependencies
uv run test-all          # ❌ Hangs due to tour tests

# If tests fail unexpectedly, restart container:
docker restart odoo-opw-script-runner-1

# Debug specific test
python tools/test_runner.py python TestProductTemplate.test_name_field_validation -v

# Check container status
docker ps | grep odoo-opw

# View test logs
ls -la tmp/tests/  # List all test runs
cat tmp/tests/odoo-tests-*/gpt_summary.txt  # Quick summary
```

## Key Files to Review

1. **JavaScript Test Registration**:
   - `addons/product_connect/__manifest__.py` - Check 'assets' section
   - `addons/product_connect/static/tests/` - Verify test files exist
   - `addons/product_connect/tests/__init__.py` - Check test imports

2. **Test Runner**:
   - `tools/test_runner.py` - Main test orchestration
   - Line 995: Database setup TODO
   - Line 256-267: Critical error detection logic

3. **Test Fixtures**:
   - `addons/product_connect/tests/fixtures/base.py` - Authentication setup
   - `addons/product_connect/tests/test_helpers.py` - SKU generation

## Context for Next Developer

### ✅ SUCCESS: Python tests are fully working!
- Unit tests: 130/130 passing
- Integration tests: 195/195 passing
- Total: 325/325 Python tests passing

### ⚠️ CRITICAL: Don't change test_runner.py tag format!
The GPT agent tried to "fix" the tag format but actually broke unit tests. The current format in commit 48dc13f works perfectly. DO NOT CHANGE IT.

### 📝 Only remaining issue: Tour tests JavaScript dependencies
The JavaScript test files exist in `addons/product_connect/static/tests/` but fail to load due to incorrect asset bundling in `__manifest__.py`. The error shows module paths like `@product_connect/../tests/helpers/test_base` which suggests the bundling configuration needs adjustment.

**Suggested fix approach:**
1. Review Odoo 18 documentation for JavaScript test asset bundling
2. Update `__manifest__.py` assets section 
3. Separate unit test files (*.test.js) from tour files (tours/*.js) into different bundles
4. Test with `python tools/test_runner.py tour`

### 🔧 GPT Agent Usage
When using GPT agent, use `mcp__gpt-codex__codex` directly (see CLAUDE.md for details), NOT the Task() tool.

Good luck! 🚀