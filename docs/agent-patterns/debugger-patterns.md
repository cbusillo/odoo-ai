# 🐛 Debugger Agent - Error Analysis Patterns

This file contains detailed debugging patterns and examples extracted from the Debugger agent documentation.

## Complete Error Investigation Workflow

```python
# Comprehensive error analysis process
def investigate_error(error_traceback):
    # Phase 1: Parse and classify the error
    error_info = parse_error_details(error_traceback)
    
    # Phase 2: Gather logs and context
    container_logs = mcp__docker__fetch_container_logs(
        container_id="${ODOO_PROJECT_NAME}-web-1",
        tail="all"
    )
    
    odoo_logs = mcp__odoo-intelligence__odoo_logs(
        lines=200
    )
    
    # Phase 3: Find related code
    error_sources = mcp__odoo-intelligence__search_code(
        pattern=error_info['method_name'],
        file_type="py"
    )
    
    # Phase 4: Trace inheritance chain if model-related
    if error_info['model']:
        inheritance = mcp__odoo-intelligence__model_query(
            operation="inheritance",
            model_name=error_info['model']
        )
    
    # Phase 5: Check for similar patterns
    similar_errors = search_for_error_patterns(error_info['error_type'])
    
    return compile_diagnosis(error_info, container_logs, odoo_logs, error_sources, inheritance)
```

## Error Pattern Recognition

### AttributeError Patterns

```python
# Pattern: 'NoneType' object has no attribute 'x'
def debug_none_type_error(traceback):
    # Extract the failing attribute
    attr_pattern = r"'NoneType' object has no attribute '(\w+)'"
    attribute = re.search(attr_pattern, traceback).group(1)
    
    # Find all usages of this attribute
    usages = mcp__odoo-intelligence__search_code(
        pattern=f"\.{attribute}",
        file_type="py"
    )
    
    # Look for missing None checks
    return analyze_none_checks(usages, attribute)

# Pattern: Missing method on object
def debug_missing_method(traceback, method_name):
    # Find where method should be defined
    method_locations = mcp__odoo-intelligence__find_method(
        method_name=method_name
    )
    
    # Check inheritance chain
    if "object has no attribute" in traceback:
        model_name = extract_model_from_traceback(traceback)
        inheritance = mcp__odoo-intelligence__model_query(
            operation="inheritance",
            model_name=model_name
        )
        
        return check_method_availability(method_locations, inheritance)
```

### Database Error Patterns

```python
# Pattern: UniqueViolation
def debug_unique_violation(error_message):
    # Extract constraint name
    constraint_match = re.search(r'constraint "([^"]+)"', error_message)
    constraint_name = constraint_match.group(1) if constraint_match else None
    
    # Find constraint definition
    constraint_code = mcp__odoo-intelligence__search_code(
        pattern=f"unique.*{constraint_name}|_sql_constraints",
        file_type="py"
    )
    
    # Check for duplicate prevention logic
    duplicate_checks = mcp__odoo-intelligence__search_code(
        pattern="exists.*domain|search_count",
        file_type="py"
    )
    
    return analyze_uniqueness_handling(constraint_code, duplicate_checks)

# Pattern: psycopg2.OperationalError
def debug_database_connection(error_message):
    # Check container status
    containers = mcp__docker__list_containers()
    db_container = [c for c in containers if 'database' in c['name']]
    
    # Get database logs
    if db_container:
        db_logs = mcp__docker__fetch_container_logs(
            container_id=db_container[0]['id'],
            tail=100
        )
        
        return analyze_db_connectivity(db_logs, error_message)

# Pattern: IntegrityError (Foreign Key)
def debug_foreign_key_error(error_message):
    # Extract referenced table/field
    fk_pattern = r'foreign key constraint "([^"]+)"'
    constraint = re.search(fk_pattern, error_message)
    
    if constraint:
        # Find model relationships
        relationships = mcp__odoo-intelligence__search_code(
            pattern=f"Many2one.*{constraint.group(1)}|fields\.Many2one",
            file_type="py"
        )
        
        return analyze_relationship_integrity(relationships, error_message)
```

### Access Rights Debug Patterns

```python
# Pattern: AccessError debugging
def debug_access_error(user_id, model_name, operation):
    # Check user's access rights
    access_analysis = mcp__odoo-intelligence__permission_checker(
        user=str(user_id),
        model=model_name,
        operation=operation
    )
    
    # Find access rules
    access_rules = mcp__odoo-intelligence__search_code(
        pattern=f"ir\.model\.access.*{model_name}|ir\.rule.*{model_name}",
        file_type="xml"
    )
    
    # Check group memberships
    user_groups = mcp__odoo-intelligence__execute_code(
        code=f"""
        user = env['res.users'].browse({user_id})
        groups = user.groups_id.mapped('name')
        print("User groups:", groups)
        """
    )
    
    return compile_access_diagnosis(access_analysis, access_rules, user_groups)
```

### Performance Error Patterns

```python
# Pattern: Memory/Timeout errors
def debug_performance_error(error_type):
    # Get performance analysis
    perf_issues = mcp__odoo-intelligence__analysis_query(
        analysis_type="performance",
        model_name=extract_model_from_context()
    )
    
    # Look for N+1 queries
    query_patterns = mcp__odoo-intelligence__search_code(
        pattern="for.*in.*:|\.mapped\(|\.filtered\(",
        file_type="py"
    )
    
    # Check batch operations
    batch_operations = mcp__odoo-intelligence__search_code(
        pattern="@api\.model_create_multi|\.create\(\[|\.write\(\{",
        file_type="py"
    )
    
    return analyze_performance_bottlenecks(perf_issues, query_patterns, batch_operations)

# Pattern: RecursionError
def debug_recursion_error(traceback):
    # Find recursive calls in traceback
    call_stack = extract_call_stack(traceback)
    recursive_method = find_recursive_pattern(call_stack)
    
    # Search for recursive implementations
    recursive_code = mcp__odoo-intelligence__search_code(
        pattern=f"def {recursive_method}.*:.*{recursive_method}",
        file_type="py"
    )
    
    return analyze_recursion_issue(recursive_code, call_stack)
```

## Shopify Integration Debug Patterns

```python
# Pattern: GraphQL errors
def debug_shopify_graphql_error(error_response):
    # Extract GraphQL query from error
    query_pattern = r'query: (.+?)(?=\n|$)'
    query = re.search(query_pattern, error_response)
    
    # Find related Shopify code
    shopify_code = mcp__odoo-intelligence__search_code(
        pattern="shopify.*gql|graphql.*query",
        file_type="py"
    )
    
    # Check API rate limits
    rate_limit_code = mcp__odoo-intelligence__search_code(
        pattern="rate.*limit|429|too.*many.*requests",
        file_type="py"
    )
    
    return analyze_shopify_api_error(query, shopify_code, rate_limit_code, error_response)

# Pattern: Webhook failures
def debug_shopify_webhook_error(webhook_data):
    # Find webhook handlers
    webhook_handlers = mcp__odoo-intelligence__search_code(
        pattern="@route.*webhook|def.*webhook",
        file_type="py"
    )
    
    # Check webhook validation
    validation_code = mcp__odoo-intelligence__search_code(
        pattern="hmac|webhook.*valid|verify.*webhook",
        file_type="py"
    )
    
    # Get recent webhook logs
    webhook_logs = mcp__docker__fetch_container_logs(
        container_id="${ODOO_PROJECT_NAME}-web-1",
        tail=50
    )
    
    return analyze_webhook_failure(webhook_handlers, validation_code, webhook_logs)
```

## View/Template Error Patterns

```python
# Pattern: QWebException
def debug_qweb_error(template_error):
    # Extract template and field info
    template_name = extract_template_name(template_error)
    field_name = extract_field_name(template_error)
    
    # Find template definition
    template_def = mcp__odoo-intelligence__search_code(
        pattern=f'id="{template_name}"',
        file_type="xml"
    )
    
    # Check field existence
    if field_name:
        field_info = mcp__odoo-intelligence__search_code(
            pattern=f"{field_name}.*=.*fields\.",
            file_type="py"
        )
        
        return analyze_template_field_error(template_def, field_info, template_error)

# Pattern: Template not found
def debug_missing_template(template_id):
    # Search for template definitions
    template_search = mcp__odoo-intelligence__search_code(
        pattern=f'template.*{template_id}|id="{template_id}"',
        file_type="xml"
    )
    
    # Check module dependencies
    dependencies = mcp__odoo-intelligence__addon_dependencies(
        addon_name=extract_current_addon()
    )
    
    return analyze_template_availability(template_search, dependencies)
```

## Stack Trace Analysis Patterns

```python
# Systematic stack trace analysis
def analyze_stack_trace(traceback):
    frames = parse_traceback_frames(traceback)
    
    analysis = {
        'entry_point': frames[0],  # Where error originated
        'error_location': frames[-1],  # Where error occurred
        'custom_code_frames': [f for f in frames if is_custom_code(f)],
        'framework_frames': [f for f in frames if is_framework_code(f)],
        'critical_path': identify_critical_path(frames)
    }
    
    # Focus on custom code in critical path
    for frame in analysis['custom_code_frames']:
        frame['code_context'] = get_code_context(frame['file'], frame['line'])
        frame['recent_changes'] = check_recent_git_changes(frame['file'])
    
    return analysis

def identify_error_category(error_type, message, traceback):
    """Classify errors for targeted debugging."""
    categories = {
        'data_integrity': ['IntegrityError', 'ValidationError'],
        'access_control': ['AccessError', 'UserError'],
        'performance': ['MemoryError', 'TimeoutError'],
        'integration': ['ConnectionError', 'APIError'],
        'logic': ['AttributeError', 'KeyError', 'IndexError'],
        'configuration': ['ImportError', 'ConfigurationError']
    }
    
    for category, error_types in categories.items():
        if any(et in str(error_type) for et in error_types):
            return category
    
    return 'unknown'
```

## Error Recovery Patterns

```python
# Automatic error recovery suggestions
def suggest_recovery_actions(error_analysis):
    """Provide actionable recovery steps."""
    
    recovery_actions = []
    
    if error_analysis['category'] == 'data_integrity':
        recovery_actions.extend([
            "Check for duplicate data before creation",
            "Add validation in model constraints",
            "Review @api.constrains decorators"
        ])
    
    elif error_analysis['category'] == 'access_control':
        recovery_actions.extend([
            "Review ir.model.access records",
            "Check ir.rule conditions", 
            "Verify user group memberships"
        ])
    
    elif error_analysis['category'] == 'performance':
        recovery_actions.extend([
            "Add database indexes for frequent searches",
            "Use read_group instead of loops",
            "Implement batch operations"
        ])
    
    elif error_analysis['category'] == 'integration':
        recovery_actions.extend([
            "Check API credentials and endpoints",
            "Review rate limiting logic",
            "Add retry mechanisms with backoff"
        ])
    
    # Add specific code suggestions
    if error_analysis.get('suggested_fixes'):
        recovery_actions.extend(error_analysis['suggested_fixes'])
    
    return recovery_actions

# Route complex errors to other agents
def route_complex_error(error_analysis):
    """Determine if error needs specialist attention."""
    
    if error_analysis['category'] == 'performance':
        return Task(
            description="Performance optimization needed",
            prompt=f"@docs/agents/flash.md\n\nOptimize performance issues: {error_analysis}",
            subagent_type="flash"
        )
    
    elif 'container' in error_analysis.get('context', ''):
        return Task(
            description="Container issue diagnosis",
            prompt=f"@docs/agents/dock.md\n\nDiagnose container problem: {error_analysis}",
            subagent_type="dock"
        )
    
    elif len(error_analysis.get('affected_files', [])) > 5:
        return Task(
            description="Complex multi-file analysis",
            prompt=f"@docs/agents/gpt.md\n\nAnalyze complex error: {error_analysis}",
            subagent_type="gpt"
        )
    
    return None  # Handle locally
```

## Testing Error Patterns

```python
# Pattern: Test failures
def debug_test_failure(test_output):
    # Extract test method and assertion
    test_method = extract_test_method(test_output)
    assertion_error = extract_assertion_details(test_output)
    
    # Find test code
    test_code = mcp__odoo-intelligence__search_code(
        pattern=f"def {test_method}",
        file_type="py"
    )
    
    # Check test data setup
    test_data = mcp__odoo-intelligence__search_code(
        pattern="setUpClass|setUp|self\.env\.ref",
        file_type="py"
    )
    
    return analyze_test_failure(test_code, test_data, assertion_error)

# Pattern: Tour test failures
def debug_tour_failure(tour_error):
    # Get browser logs
    browser_logs = mcp__playwright__browser_console_messages()
    
    # Check for JS errors
    js_errors = [log for log in browser_logs if log['level'] == 'error']
    
    # Take screenshot for visual debugging
    screenshot = mcp__playwright__browser_take_screenshot()
    
    # Get accessibility tree
    snapshot = mcp__playwright__browser_snapshot()
    
    return analyze_tour_failure(js_errors, screenshot, snapshot, tour_error)
```

## Logging and Monitoring Patterns

```python
# Enhanced error logging
def log_error_context(error, context=None):
    """Log errors with rich context for debugging."""
    
    error_data = {
        'timestamp': datetime.now().isoformat(),
        'error_type': type(error).__name__,
        'error_message': str(error),
        'traceback': traceback.format_exc(),
        'context': context or {},
        'environment': {
            'user_id': env.user.id if hasattr(env, 'user') else None,
            'company_id': env.company.id if hasattr(env, 'company') else None,
            'lang': env.lang if hasattr(env, 'lang') else None,
        },
        'request_data': {
            'url': getattr(request, 'httprequest', {}).get('url'),
            'method': getattr(request, 'httprequest', {}).get('method'),
            'user_agent': getattr(request, 'httprequest', {}).get('user_agent'),
        } if 'request' in globals() else {}
    }
    
    _logger.error("Detailed error context: %s", json.dumps(error_data, indent=2))
    return error_data

# Pattern: Monitoring for recurring errors
def check_error_patterns():
    """Identify recurring error patterns."""
    
    # Get recent logs
    recent_logs = mcp__odoo-intelligence__odoo_logs(lines=1000)
    
    # Extract error patterns
    error_patterns = {}
    for line in recent_logs.split('\n'):
        if 'ERROR' in line:
            error_key = extract_error_signature(line)
            error_patterns[error_key] = error_patterns.get(error_key, 0) + 1
    
    # Identify frequent errors
    frequent_errors = {k: v for k, v in error_patterns.items() if v > 5}
    
    return frequent_errors
```
