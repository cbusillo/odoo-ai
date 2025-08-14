# 🎭 Playwright Agent - Browser Testing Patterns

This file contains detailed browser testing patterns and examples extracted from the Playwright agent documentation.

## Complete Tour Test Debugging Workflow

```python
def debug_failed_tour_comprehensive(tour_name):
    """Complete debugging workflow for failed tour tests."""
    
    # Phase 1: Run the tour with monitoring
    initial_state = capture_initial_browser_state()
    
    # Start tour execution
    tour_result = Bash(f".venv/bin/python tools/test_runner.py tour --test-tags {tour_name}")
    
    # Phase 2: Capture failure context if tour failed
    if tour_result.returncode != 0:
        failure_context = {
            'console_errors': mcp__playwright__browser_console_messages(),
            'final_screenshot': mcp__playwright__browser_take_screenshot(
                filename=f"tour_failure_{tour_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            ),
            'accessibility_tree': mcp__playwright__browser_snapshot(),
            'page_source': get_page_source_snippet(),
            'network_requests': get_recent_network_activity()
        }
        
        # Phase 3: Analyze failure patterns
        failure_analysis = analyze_tour_failure_patterns(
            tour_result.stdout + tour_result.stderr,
            failure_context
        )
        
        return {
            'tour_output': tour_result.stdout + tour_result.stderr,
            'failure_context': failure_context,
            'analysis': failure_analysis,
            'recovery_suggestions': suggest_tour_recovery_actions(failure_analysis)
        }
    
    return {'status': 'success', 'tour_output': tour_result.stdout}

def capture_initial_browser_state():
    """Capture browser state before starting tour."""
    return {
        'url': get_current_url(),
        'console_clear': mcp__playwright__browser_console_messages(),  # Clear console
        'initial_screenshot': mcp__playwright__browser_take_screenshot(
            filename="tour_start_state.png"
        )
    }
```

## Interactive Debugging Patterns

### Step-by-Step Tour Execution

```python
def interactive_tour_debugging(tour_steps):
    """Execute tour steps one by one with debugging at each step."""
    
    step_results = []
    
    for i, step in enumerate(tour_steps):
        print(f"Executing step {i+1}: {step['description']}")
        
        # Take screenshot before step
        pre_screenshot = mcp__playwright__browser_take_screenshot(
            filename=f"step_{i+1}_before.png"
        )
        
        # Execute step
        try:
            step_result = execute_tour_step(step)
            
            # Wait for any animations/transitions
            mcp__playwright__browser_wait_for(time=1)
            
            # Take screenshot after step
            post_screenshot = mcp__playwright__browser_take_screenshot(
                filename=f"step_{i+1}_after.png"
            )
            
            # Verify expected outcome
            verification = verify_step_outcome(step, post_screenshot)
            
            step_results.append({
                'step_number': i+1,
                'description': step['description'],
                'success': verification['success'],
                'pre_screenshot': pre_screenshot,
                'post_screenshot': post_screenshot,
                'verification': verification,
                'console_errors': mcp__playwright__browser_console_messages()
            })
            
            if not verification['success']:
                print(f"Step {i+1} failed: {verification['reason']}")
                break
                
        except Exception as e:
            step_results.append({
                'step_number': i+1,
                'description': step['description'],
                'success': False,
                'error': str(e),
                'debug_info': get_debug_context()
            })
            break
    
    return step_results

def execute_tour_step(step):
    """Execute a single tour step with proper error handling."""
    
    if step['action'] == 'navigate':
        return mcp__playwright__browser_navigate(url=step['url'])
    
    elif step['action'] == 'click':
        # First get current page state
        snapshot = mcp__playwright__browser_snapshot()
        
        # Find element in snapshot
        element_info = find_element_in_snapshot(snapshot, step['selector'])
        
        if not element_info:
            raise Exception(f"Element not found: {step['selector']}")
        
        return mcp__playwright__browser_click(
            element=step['description'],
            ref=element_info['ref']
        )
    
    elif step['action'] == 'type':
        return mcp__playwright__browser_type(
            element=step['description'],
            ref=step['selector'],
            text=step['text']
        )
    
    elif step['action'] == 'wait':
        if step.get('text'):
            return mcp__playwright__browser_wait_for(text=step['text'])
        else:
            return mcp__playwright__browser_wait_for(time=step.get('duration', 2))
    
    else:
        raise Exception(f"Unknown action: {step['action']}")
```

## Element Interaction Patterns

### Robust Element Selection

```python
def robust_element_interaction(element_description, interaction_type, **kwargs):
    """Robust element interaction with fallback strategies."""
    
    # Strategy 1: Use accessibility tree for most reliable selection
    snapshot = mcp__playwright__browser_snapshot()
    element_ref = find_element_by_accessibility(snapshot, element_description)
    
    if element_ref:
        return execute_interaction(element_ref, interaction_type, **kwargs)
    
    # Strategy 2: Wait and retry (element might be loading)
    mcp__playwright__browser_wait_for(time=2)
    snapshot = mcp__playwright__browser_snapshot()
    element_ref = find_element_by_accessibility(snapshot, element_description)
    
    if element_ref:
        return execute_interaction(element_ref, interaction_type, **kwargs)
    
    # Strategy 3: Look for partial matches or similar elements
    similar_elements = find_similar_elements(snapshot, element_description)
    
    if similar_elements:
        print(f"Element '{element_description}' not found exactly, found similar: {similar_elements}")
        # Use best match
        best_match = similar_elements[0]
        return execute_interaction(best_match['ref'], interaction_type, **kwargs)
    
    # Strategy 4: Take screenshot and provide debug info
    debug_screenshot = mcp__playwright__browser_take_screenshot(
        filename=f"element_not_found_{datetime.now().strftime('%H%M%S')}.png"
    )
    
    raise Exception(f"""
    Element '{element_description}' not found for {interaction_type}.
    Debug screenshot saved: {debug_screenshot}
    Available elements: {extract_available_elements(snapshot)}
    """)

def find_element_by_accessibility(snapshot, description):
    """Find element using accessibility tree information."""
    
    # Parse accessibility tree for interactive elements
    interactive_elements = extract_interactive_elements(snapshot)
    
    # Look for exact matches first
    for element in interactive_elements:
        if description.lower() in element.get('name', '').lower():
            return element.get('selector')
        if description.lower() in element.get('description', '').lower():
            return element.get('selector')
    
    # Look for role-based matches
    role_keywords = {
        'button': ['button', 'btn'],
        'link': ['link', 'anchor'],
        'textbox': ['input', 'field', 'textbox'],
        'menu': ['menu', 'dropdown']
    }
    
    for role, keywords in role_keywords.items():
        if any(keyword in description.lower() for keyword in keywords):
            role_elements = [e for e in interactive_elements if e.get('role') == role]
            for element in role_elements:
                if any(keyword in element.get('name', '').lower() for keyword in keywords):
                    return element.get('selector')
    
    return None
```

### Dynamic Content Handling

```python
def handle_dynamic_content(expected_content, timeout=10):
    """Handle dynamically loaded content with smart waiting."""
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Check if content is present
        snapshot = mcp__playwright__browser_snapshot()
        
        if expected_content in snapshot:
            return True
        
        # Check for loading indicators
        loading_indicators = [
            'Loading...',
            'Please wait',
            'spinner',
            'o_loading'
        ]
        
        is_loading = any(indicator in snapshot for indicator in loading_indicators)
        
        if is_loading:
            # Content is still loading, wait longer
            mcp__playwright__browser_wait_for(time=1)
            continue
        
        # Check for error states
        error_indicators = [
            'Error',
            'Failed to load',
            'Something went wrong'
        ]
        
        has_error = any(error in snapshot for error in error_indicators)
        
        if has_error:
            raise Exception(f"Error state detected while waiting for: {expected_content}")
        
        # Wait and retry
        mcp__playwright__browser_wait_for(time=0.5)
    
    raise TimeoutError(f"Content '{expected_content}' not found within {timeout} seconds")

def wait_for_odoo_action_complete():
    """Wait for Odoo action to complete (save, create, etc.)."""
    
    # Wait for any loading spinners to disappear
    mcp__playwright__browser_wait_for(textGone="Loading...")
    
    # Wait for success/error notifications
    mcp__playwright__browser_wait_for(time=1)
    
    # Check for success indicators
    snapshot = mcp__playwright__browser_snapshot()
    
    success_indicators = [
        'saved successfully',
        'created successfully',
        'updated successfully',
        'Record saved'
    ]
    
    error_indicators = [
        'ValidationError',
        'Error!',
        'Failed to save'
    ]
    
    if any(indicator in snapshot for indicator in success_indicators):
        return {'success': True, 'message': 'Action completed successfully'}
    
    if any(indicator in snapshot for indicator in error_indicators):
        return {'success': False, 'message': 'Action failed', 'snapshot': snapshot}
    
    # No clear indication, assume success if no errors
    return {'success': True, 'message': 'Action completed (no clear indicator)'}
```

## Form Interaction Patterns

### Odoo Form Manipulation

```python
def fill_odoo_form(form_data):
    """Fill Odoo form with comprehensive field handling."""
    
    for field_name, field_value in form_data.items():
        try:
            fill_result = fill_odoo_field(field_name, field_value)
            
            if not fill_result['success']:
                return {
                    'success': False,
                    'failed_field': field_name,
                    'error': fill_result['error']
                }
        
        except Exception as e:
            return {
                'success': False,
                'failed_field': field_name,
                'error': str(e),
                'debug_snapshot': mcp__playwright__browser_snapshot()
            }
    
    return {'success': True, 'message': 'Form filled successfully'}

def fill_odoo_field(field_name, field_value):
    """Fill a specific Odoo field with type-aware handling."""
    
    # Get current form state
    snapshot = mcp__playwright__browser_snapshot()
    
    # Find field in form
    field_selector = find_field_selector(snapshot, field_name)
    
    if not field_selector:
        return {
            'success': False,
            'error': f"Field '{field_name}' not found in form"
        }
    
    # Determine field type and handle accordingly
    field_type = determine_field_type(snapshot, field_selector)
    
    if field_type == 'text':
        mcp__playwright__browser_type(
            element=f"{field_name} field",
            ref=field_selector,
            text=str(field_value)
        )
    
    elif field_type == 'select':
        mcp__playwright__browser_select_option(
            element=f"{field_name} dropdown",
            ref=field_selector,
            values=[str(field_value)]
        )
    
    elif field_type == 'many2one':
        return fill_many2one_field(field_name, field_selector, field_value)
    
    elif field_type == 'checkbox':
        # Handle boolean fields
        current_state = is_checkbox_checked(snapshot, field_selector)
        target_state = bool(field_value)
        
        if current_state != target_state:
            mcp__playwright__browser_click(
                element=f"{field_name} checkbox",
                ref=field_selector
            )
    
    else:
        return {
            'success': False,
            'error': f"Unsupported field type: {field_type}"
        }
    
    return {'success': True}

def fill_many2one_field(field_name, field_selector, field_value):
    """Handle Many2one field with dropdown and search."""
    
    # Click to open dropdown
    mcp__playwright__browser_click(
        element=f"{field_name} field",
        ref=field_selector
    )
    
    # Wait for dropdown to appear
    mcp__playwright__browser_wait_for(time=1)
    
    # Type to search
    mcp__playwright__browser_type(
        element=f"{field_name} search",
        ref=f"{field_selector} input",
        text=str(field_value)
    )
    
    # Wait for search results
    mcp__playwright__browser_wait_for(time=1)
    
    # Click first result
    mcp__playwright__browser_click(
        element="First search result",
        ref=".o_dropdown_menu .o_dropdown_item:first-child"
    )
    
    return {'success': True}
```

## Error Recovery and Debugging

### Browser Error Recovery

```python
def recover_from_browser_error(error_info):
    """Attempt to recover from browser errors."""
    
    recovery_strategies = [
        refresh_page_strategy,
        clear_browser_state_strategy,
        restart_browser_strategy,
        check_network_connectivity_strategy
    ]
    
    for strategy in recovery_strategies:
        try:
            result = strategy(error_info)
            
            if result['success']:
                return {
                    'recovered': True,
                    'strategy_used': strategy.__name__,
                    'result': result
                }
        
        except Exception as e:
            continue  # Try next strategy
    
    return {
        'recovered': False,
        'error': 'All recovery strategies failed',
        'final_state': capture_browser_debug_info()
    }

def refresh_page_strategy(error_info):
    """Try to recover by refreshing the page."""
    
    current_url = get_current_url_from_browser()
    
    mcp__playwright__browser_navigate(url=current_url)
    mcp__playwright__browser_wait_for(time=3)
    
    # Check if page loaded successfully
    snapshot = mcp__playwright__browser_snapshot()
    
    if 'error' not in snapshot.lower() and len(snapshot) > 100:
        return {'success': True, 'message': 'Page refreshed successfully'}
    
    return {'success': False, 'message': 'Page refresh did not resolve issue'}

def clear_browser_state_strategy(error_info):
    """Clear browser state and reload."""
    
    # Clear console messages
    mcp__playwright__browser_console_messages()
    
    # Navigate to a clean state
    mcp__playwright__browser_navigate(url="http://localhost:8069/web")
    mcp__playwright__browser_wait_for(time=5)
    
    # Check if we're in a clean state
    snapshot = mcp__playwright__browser_snapshot()
    
    if 'login' in snapshot.lower() or 'odoo' in snapshot.lower():
        return {'success': True, 'message': 'Browser state cleared'}
    
    return {'success': False, 'message': 'Could not clear browser state'}

def capture_browser_debug_info():
    """Capture comprehensive debug information."""
    
    return {
        'timestamp': datetime.now().isoformat(),
        'url': get_current_url_from_browser(),
        'console_messages': mcp__playwright__browser_console_messages(),
        'screenshot': mcp__playwright__browser_take_screenshot(
            filename=f"debug_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        ),
        'accessibility_tree': mcp__playwright__browser_snapshot(),
        'page_title': extract_page_title_from_snapshot()
    }
```

## Performance Testing Patterns

### Load Time Measurement

```python
def measure_page_performance(url):
    """Measure page load performance."""
    
    start_time = time.time()
    
    # Navigate to page
    mcp__playwright__browser_navigate(url=url)
    
    # Wait for basic page load
    mcp__playwright__browser_wait_for(time=1)
    
    # Wait for dynamic content
    wait_for_odoo_page_ready()
    
    end_time = time.time()
    load_time = end_time - start_time
    
    # Capture performance metrics
    console_messages = mcp__playwright__browser_console_messages()
    performance_logs = [msg for msg in console_messages if 'performance' in msg.get('text', '').lower()]
    
    return {
        'url': url,
        'load_time_seconds': load_time,
        'performance_logs': performance_logs,
        'console_errors': [msg for msg in console_messages if msg.get('level') == 'error'],
        'final_snapshot': mcp__playwright__browser_snapshot()
    }

def wait_for_odoo_page_ready():
    """Wait for Odoo page to be fully ready."""
    
    # Wait for common Odoo loading indicators to disappear
    loading_indicators = [
        'o_loading',
        'Loading...',
        'fa-spinner'
    ]
    
    for indicator in loading_indicators:
        try:
            mcp__playwright__browser_wait_for(textGone=indicator)
        except:
            pass  # Indicator might not be present
    
    # Wait for basic Odoo UI elements
    mcp__playwright__browser_wait_for(time=2)
    
    # Check if page is interactive
    snapshot = mcp__playwright__browser_snapshot()
    interactive_elements = count_interactive_elements(snapshot)
    
    if interactive_elements < 3:
        # Page might still be loading
        mcp__playwright__browser_wait_for(time=3)
```

## Test Data Management

### Test Environment Setup

```python
def setup_browser_test_environment():
    """Set up browser for testing with proper authentication."""
    
    # Navigate to login page
    mcp__playwright__browser_navigate(url="http://localhost:8069/web/login")
    
    # Check if already logged in
    snapshot = mcp__playwright__browser_snapshot()
    
    if 'login' not in snapshot.lower():
        # Already logged in
        return {'success': True, 'message': 'Already authenticated'}
    
    # Perform login
    login_result = perform_test_login()
    
    if not login_result['success']:
        return login_result
    
    # Set up test data context
    setup_result = setup_test_data_context()
    
    return {
        'success': True,
        'login_result': login_result,
        'test_data_setup': setup_result
    }

def perform_test_login():
    """Perform login for test environment."""
    
    # Fill login form
    mcp__playwright__browser_type(
        element="Username field",
        ref="input[name='login']",
        text="admin"
    )
    
    mcp__playwright__browser_type(
        element="Password field", 
        ref="input[name='password']",
        text="admin"
    )
    
    # Submit form
    mcp__playwright__browser_click(
        element="Login button",
        ref="button[type='submit']"
    )
    
    # Wait for redirect
    mcp__playwright__browser_wait_for(time=3)
    
    # Verify login success
    snapshot = mcp__playwright__browser_snapshot()
    
    if 'Apps' in snapshot or 'dashboard' in snapshot.lower():
        return {'success': True, 'message': 'Login successful'}
    
    return {'success': False, 'message': 'Login failed', 'snapshot': snapshot}

def setup_test_data_context():
    """Set up necessary test data context."""
    
    # Navigate to test module
    mcp__playwright__browser_navigate(url="http://localhost:8069/web#action=product_connect.action_motor_list")
    
    # Wait for page load
    mcp__playwright__browser_wait_for(time=3)
    
    # Verify we're in the right context
    snapshot = mcp__playwright__browser_snapshot()
    
    if 'motor' in snapshot.lower() or 'product' in snapshot.lower():
        return {'success': True, 'message': 'Test context ready'}
    
    return {'success': False, 'message': 'Failed to set up test context'}
```

## Integration with Other Agents

### Agent Collaboration Patterns

```python
# Called by Scout agent for tour test debugging
def debug_tour_for_scout(tour_name, failure_output):
    """Debug tour test failure for Scout agent."""
    
    # Parse Scout's failure output
    failure_analysis = parse_scout_failure_output(failure_output)
    
    # Run interactive debugging
    debug_result = debug_failed_tour_comprehensive(tour_name)
    
    # Provide actionable feedback to Scout
    return {
        'playwright_debug': debug_result,
        'suggested_fixes': generate_scout_feedback(failure_analysis, debug_result),
        'test_recommendations': recommend_test_improvements(debug_result)
    }

# Called by Owl agent for frontend debugging
def debug_frontend_issue(component_name, issue_description):
    """Debug frontend component issues for Owl agent."""
    
    # Navigate to component area
    navigation_result = navigate_to_component(component_name)
    
    if not navigation_result['success']:
        return navigation_result
    
    # Capture frontend state
    frontend_state = {
        'console_errors': mcp__playwright__browser_console_messages(),
        'dom_snapshot': mcp__playwright__browser_snapshot(),
        'screenshot': mcp__playwright__browser_take_screenshot(),
        'network_activity': capture_network_activity()
    }
    
    # Analyze for frontend issues
    analysis = analyze_frontend_issues(frontend_state, issue_description)
    
    return {
        'frontend_state': frontend_state,
        'analysis': analysis,
        'owl_recommendations': generate_owl_recommendations(analysis)
    }

def generate_scout_feedback(failure_analysis, debug_result):
    """Generate actionable feedback for Scout agent."""
    
    feedback = []
    
    if 'element not found' in failure_analysis.get('error_type', ''):
        feedback.append({
            'type': 'selector_update',
            'current_selector': failure_analysis.get('selector'),
            'suggested_selector': extract_working_selector(debug_result),
            'reason': 'Element selector needs updating'
        })
    
    if debug_result.get('failure_context', {}).get('console_errors'):
        js_errors = debug_result['failure_context']['console_errors']
        feedback.append({
            'type': 'js_error',
            'errors': js_errors,
            'suggestion': 'Fix JavaScript errors before running tour'
        })
    
    return feedback
```