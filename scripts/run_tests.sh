#!/bin/bash

echo "=== Odoo 18 Product Connect Test Runner ==="
echo "=========================================="
echo ""

# Detect environment
if command -v docker >/dev/null 2>&1 && [ -f "docker-compose.yml" ]; then
    ENVIRONMENT="docker"
    echo "🐳 Detected Docker environment"
elif [ -d "/volumes/addons" ] && [ -d "/odoo" ]; then
    ENVIRONMENT="codex"
    echo "☁️  Detected Codex Cloud environment"
    DB_NAME="${ODOO_DB:-opw}"
else
    echo "❌ Could not detect environment. Expected either:"
    echo "   - Docker: docker command + docker-compose.yml"
    echo "   - Codex Cloud: /volumes/addons + /odoo directories"
    exit 1
fi

echo ""
echo "Usage: $0 [test_type]"
echo ""
echo "Test types:"
echo "  all (default) - Run all test layers"
echo "  python        - Run only Python unit tests"  
echo "  js            - Run only JavaScript tests"
echo "  tour          - Run only tour tests"
echo "  [tag]         - Run specific test tag (e.g., TestOrderImporter, +TestCustomerImporter)"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test result tracking
TESTS_PASSED=0
TESTS_FAILED=0

# Function to get random available port
get_random_port() {
    local port
    while true; do
        port=$((RANDOM % 10000 + 8080))  # Random port between 8080-18079
        if ! netstat -tuln | grep -q ":$port "; then
            echo "$port"
            return
        fi
    done
}

# Function to run commands based on environment
run_odoo_command() {
    local cmd_args="$1"
    local timeout_seconds="${2:-180}"  # Default 3 minutes
    
    if [ "$ENVIRONMENT" = "docker" ]; then
        local port
        port=$(get_random_port)
        echo "Using port: $port"
        timeout "$timeout_seconds" docker exec odoo-opw-script-runner-1 /odoo/odoo-bin -d opw --http-port="$port" "$cmd_args"
    else
        timeout "$timeout_seconds" /odoo/odoo-bin -d "$DB_NAME" "$cmd_args"
    fi
}

# Function to get addons path
get_addons_path() {
    if [ "$ENVIRONMENT" = "docker" ]; then
        echo "/volumes/addons,/odoo/addons,/volumes/enterprise"
    else
        echo "/workspace/addons,/odoo/addons,/volumes/enterprise"
    fi
}

# Function to run tests
run_test() {
    local test_name=$1
    local test_args="$2"
    local timeout_seconds="${3:-240}"  # Default 4 minutes for tests
    local addons_path
    addons_path=$(get_addons_path)
    
    echo -e "\n${BLUE}Running: ${test_name}${NC}"
    echo "Command: run_odoo_command \"$test_args --addons-path=$addons_path\" $timeout_seconds"
    echo "----------------------------------------"
    
    # Run test and capture output
    local output
    output=$(run_odoo_command "$test_args --addons-path=$addons_path" "$timeout_seconds" 2>&1)
    local exit_code=$?
    
    # Display relevant output (filter out noise)
    echo "$output" | grep -E "(FAIL|ERROR|test_|Ran [0-9]+ tests|OK|Module.*tests|Starting.*test|\.\.\.|passed|failed)" | tail -50
    
    # Extract test counts from output
    local tests_run=0
    local tests_ok=0
    local tests_failed=0
    local errors=0
    local total=0
    
    # Look for test results in output
    if echo "$output" | grep -q "Module product_connect:.*tests"; then
        local test_line
        test_line=$(echo "$output" | grep "Module product_connect:.*tests" | tail -1)
        tests_failed=$(echo "$test_line" | grep -o "[0-9]* failures" | grep -o "[0-9]*" | head -1 | tr -d '\n' || echo "0")
        errors=$(echo "$test_line" | grep -o "[0-9]* errors" | grep -o "[0-9]*" | head -1 | tr -d '\n' || echo "0")
        total=$(echo "$test_line" | grep -o "of [0-9]* tests" | grep -o "[0-9]*" | head -1 | tr -d '\n' || echo "0")
        if [[ -n "$total" && "$total" != "0" ]]; then
            tests_run="$total"
            tests_ok=$(( total - tests_failed - errors ))
        fi
    fi
    
    # If we couldn't parse counts, try to count test methods from output
    if [[ ${tests_run:-0} -eq 0 ]]; then
        tests_run=$(echo "$output" | grep -c "Starting.*test_" | tr -d '\n' || echo "0")
        if echo "$output" | grep -q "failed, 0 error(s) of.*tests"; then
            local result_line
            result_line=$(echo "$output" | grep "failed, 0 error(s) of.*tests" | tail -1)
            local parsed_run
            parsed_run=$(echo "$result_line" | grep -o "of [0-9]* tests" | grep -o "[0-9]*" | head -1 | tr -d '\n')
            local parsed_failed
            parsed_failed=$(echo "$result_line" | grep -o "^[0-9]* failed" | grep -o "[0-9]*" | head -1 | tr -d '\n' || echo "0")
            if [[ -n "$parsed_run" ]]; then
                tests_run="$parsed_run"
                tests_failed="$parsed_failed"
                tests_ok=$(( parsed_run - parsed_failed ))
            fi
        fi
    fi
    
    # Check for timeout
    if [[ $exit_code -eq 124 ]]; then
        echo -e "${RED}⏰ ${test_name} timed out after ${timeout_seconds}s${NC}"
        ((TESTS_FAILED++))
        return 1
    elif [[ $exit_code -eq 0 ]]; then
        if [[ ${tests_run:-0} -gt 0 ]]; then
            echo -e "${GREEN}✓ ${test_name} passed (${tests_ok:-0}/${tests_run} tests)${NC}"
        else
            echo -e "${GREEN}✓ ${test_name} passed${NC}"
        fi
        ((TESTS_PASSED++))
        return 0
    else
        if [[ ${tests_run:-0} -gt 0 ]]; then
            echo -e "${RED}✗ ${test_name} failed (${tests_ok:-0}/${tests_run} tests passed, ${tests_failed:-0} failed)${NC}"
        else
            echo -e "${RED}✗ ${test_name} failed (exit code: $exit_code)${NC}"
        fi
        ((TESTS_FAILED++))
        return 1
    fi
}

# Parse command line arguments
TEST_TYPE="${1:-all}"

# Show help and exit if requested
if [[ "$TEST_TYPE" == "--help" || "$TEST_TYPE" == "-h" ]]; then
    exit 0
fi

# Update module first (with shorter timeout)
if [[ "$TEST_TYPE" != "skip-update" ]]; then
    echo -e "${YELLOW}Updating product_connect module...${NC}"
    addons_path=$(get_addons_path)
    update_output=$(run_odoo_command "-u product_connect --stop-after-init --addons-path=$addons_path --max-cron-threads=0" 120 2>&1)
    update_exit=$?
    if [[ $update_exit -ne 0 ]]; then
        echo -e "${RED}Failed to update module. Exit code: $update_exit${NC}"
        echo "$update_output" | tail -20
        exit 1
    fi
    echo -e "${GREEN}Module updated successfully${NC}"
fi

case "$TEST_TYPE" in
    "python"|"unit")
        echo -e "\n${YELLOW}Running Python Unit Tests Only${NC}"
        run_test "Python Unit Tests" "--log-level=warn --stop-after-init --test-tags=product_connect --max-cron-threads=0"
        ;;
        
    "js"|"javascript")
        echo -e "\n${YELLOW}Running JavaScript Tests Only${NC}"
        run_test "JavaScript Integration Tests" "--log-level=warn --test-tags=product_connect_js --max-cron-threads=0"
        ;;
        
    "tour"|"tours")
        echo -e "\n${YELLOW}Running Tour Tests Only${NC}"
        run_test "Tour Tests" "--log-level=warn --test-tags=product_connect_tour --max-cron-threads=0"
        ;;
        
    "all")
        echo -e "\n${YELLOW}Running All Tests (Default)${NC}"
        
        # Run Python Unit Tests
        run_test "Python Unit Tests" "--log-level=warn --stop-after-init --test-tags=product_connect --max-cron-threads=0" 360
        
        # Run JavaScript Integration Tests
        run_test "JavaScript Integration Tests" "--log-level=warn --test-tags=product_connect_js --max-cron-threads=0" 180
        
        # Run Tour Tests
        run_test "Tour Tests" "--log-level=warn --test-tags=product_connect_tour --max-cron-threads=0" 180
        ;;
        
    *)
        # Custom test tag - use directly
        test_tag="$TEST_TYPE"
        # Add + prefix if not already present and not starting with -
        if [[ ! "$test_tag" =~ ^[+-] ]]; then
            test_tag="+$test_tag"
        fi
        echo -e "\n${YELLOW}Running Custom Test Tag: $test_tag${NC}"
        run_test "Test Tag: $test_tag" "--log-level=warn --stop-after-init --test-tags=$test_tag --max-cron-threads=0" 300
        ;;
esac

# Summary
echo -e "\n${YELLOW}=== Test Summary ===${NC}"
echo -e "Tests passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Tests failed: ${RED}${TESTS_FAILED}${NC}"

if [[ $TESTS_FAILED -eq 0 && $TESTS_PASSED -gt 0 ]]; then
    echo -e "\n${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}Some tests failed!${NC}"
    exit 1
fi