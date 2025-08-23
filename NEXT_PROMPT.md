# NEXT_PROMPT.md

## Test Runner Status - Jan 23, 2025

### ✅ What's Working

1. **Unit Tests**: 133 tests running successfully (46.6s)
   - JavaScript unit tests included (5 test methods running 12 JS test files) 
   - Chrome browser launching properly for JS tests
   - Clean database creation working
   - Proper module filtering to avoid Odoo core tests

2. **Integration Tests**: 195 tests running successfully (20.7s)
   - Production database cloning working
   - Proper test isolation

3. **Test Discovery**: 350+ total tests available
   - Python unit: ~128 tests
   - JavaScript unit: 5 test methods (12 JS files)
   - Python integration: 195 tests
   - Tour tests: Additional UI tests

4. **Infrastructure Improvements**:
   - Enhanced stall detection with diagnostics
   - Process cleanup prevents zombies
   - Adaptive timeouts based on test phase
   - Simplified Chrome flags (just 3 essential ones)
   - Tests continue running even when some fail (progressive mode)

### ❌ What Still Needs Work

## CRITICAL: Tour Tests Not Working

Tour tests are currently broken and need fixing. The issues include:

1. **Browser Launch Issues**:
   - Chrome/Chromium may not be launching properly in Docker
   - Headless mode configuration may need adjustment
   - Browser flags simplified but may need more for tours

2. **JavaScript Dependency Errors**:
   - Previous logs showed: "cannot find a definition for model 'sale.order'"
   - Tour tests trying to access models not available in test database
   - May need proper module dependencies or data setup

3. **Timeout Issues**:
   - Tours may be timing out before completion
   - Current timeout is 300 seconds but may need adjustment
   - Stall detection may be killing tours prematurely

### How to Run Tests

```bash
# Run all tests progressively (unit → integration → tour)
python tools/test_runner.py --all

# Run specific categories
python tools/test_runner.py --unit-only      # 133 tests
python tools/test_runner.py --integration-only # 195 tests
python tools/test_runner.py --tour-only       # Currently broken

# Run Python tests (unit + integration)
python tools/test_runner.py python            # 328 tests
```

### Next Steps for Tour Tests

1. **Investigate Browser Setup**:
   - Check if Chrome/Chromium is properly installed in Docker
   - Verify browser binary path and permissions
   - Test browser launch independently

2. **Fix Model Dependencies**:
   - Tour tests need sale.order and other models
   - May need to install sale module or mock the models
   - Check tour test base class setup in `addons/product_connect/tests/fixtures/base.py`

3. **Debug Tour Execution**:
   - Add more logging around browser launch
   - Check JavaScript console errors
   - Verify tour scripts are loading properly

4. **Test Files to Check**:
   - `/addons/product_connect/tests/fixtures/base.py` - TourTestCase setup
   - `/addons/product_connect/tests/tour/` - Tour test implementations
   - `/addons/product_connect/static/tests/tours/` - Tour JavaScript files

### Recent Changes Summary

The test runner has been significantly improved with better process handling, diagnostics, and the ability to run all 350+ tests. The main remaining issue is getting tour tests to work properly in the Docker environment.

Key improvements in this session:
- Fixed test discovery (was only running 10 tests, now runs 350+)
- Added stall diagnostics with process dumps
- Simplified Chrome configuration
- Made tests continue on failure for complete runs
- Added adaptive timeouts for different test phases

The test runner is now stable for unit and integration tests. Focus should be on fixing tour test execution.