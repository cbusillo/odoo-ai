# 🚢 Dock Agent - Docker Operations Patterns

This file contains detailed Docker operations patterns and examples extracted from the Dock agent documentation.

## Container Management Workflows

### Complete Health Check Pattern

```python
def comprehensive_container_health_check():
    """Complete container health assessment."""

    # Phase 1: List all containers with status
    containers = mcp__docker__list_containers(all=True)

    # Phase 2: Check Odoo-specific status
    odoo_status = mcp__odoo - intelligence__odoo_status(verbose=True)

    # Phase 3: Get logs for problematic containers
    problematic_containers = [c for c in containers if c['State'] != 'running']

    container_diagnostics = {}
    for container in problematic_containers:
        container_diagnostics[container['Names'][0]] = {
            'logs': mcp__docker__fetch_container_logs(
                container_id=container['Id'],
                tail=100
            ),
            'status': container['State'],
            'created': container['Created']
        }

    return {
        'containers': containers,
        'odoo_status': odoo_status,
        'diagnostics': container_diagnostics
    }
```

### Container Restart Patterns

```python
# Graceful restart pattern
def graceful_odoo_restart():
    """Restart Odoo services with proper sequence."""

    # Step 1: Stop web service first (stop accepting requests)
    mcp__odoo - intelligence__odoo_restart(services="web-1")

    # Step 2: Wait for current requests to finish
    time.sleep(5)

    # Step 3: Restart shell and script-runner
    mcp__odoo - intelligence__odoo_restart(services="shell-1,script-runner-1")

    # Step 4: Verify all services are healthy
    return mcp__odoo - intelligence__odoo_status()


# Emergency restart pattern
def emergency_restart():
    """Force restart when graceful restart fails."""

    # Stop all containers
    containers = mcp__docker__list_containers()
    odoo_containers = [c for c in containers if '${ODOO_PROJECT_NAME}' in c['Names'][0]]

    for container in odoo_containers:
        mcp__docker__stop_container(container_id=container['Id'])

    # Wait for clean shutdown
    time.sleep(10)

    # Start containers in dependency order
    # 1. Database first
    db_container = [c for c in odoo_containers if 'database' in c['Names'][0]]
    if db_container:
        mcp__docker__start_container(container_id=db_container[0]['Id'])
        time.sleep(15)  # Wait for database to be ready

    # 2. Then application containers
    app_containers = [c for c in odoo_containers if 'database' not in c['Names'][0]]
    for container in app_containers:
        mcp__docker__start_container(container_id=container['Id'])
        time.sleep(5)

    return mcp__odoo - intelligence__odoo_status()
```

## Module Management Patterns

### Safe Module Update Pattern

```python
def safe_module_update(module_names, test_after=True):
    """Update modules with rollback capability."""

    # Pre-update checks
    initial_status = mcp__odoo - intelligence__odoo_status()
    if not initial_status.get('healthy', False):
        raise Exception("System not healthy before update")

    # Create database backup point (if needed for critical updates)
    backup_info = create_backup_point() if is_critical_update(module_names) else None

    try:
        # Update modules using script-runner
        update_result = mcp__odoo - intelligence__odoo_update_module(
            modules=module_names,
            force_install=False
        )

        # Verify update success
        if "CRITICAL" in update_result or "ERROR" in update_result:
            raise Exception(f"Module update failed: {update_result}")

        # Test functionality if requested
        if test_after:
            test_result = run_smoke_tests()
            if not test_result['success']:
                raise Exception(f"Post-update tests failed: {test_result['errors']}")

        return {
            'success': True,
            'modules_updated': module_names,
            'update_output': update_result
        }

    except Exception as e:
        # Rollback if backup was created
        if backup_info:
            restore_from_backup(backup_info)

        return {
            'success': False,
            'error': str(e),
            'rollback_performed': backup_info is not None
        }


# Module dependency management
def update_with_dependencies(primary_module):
    """Update module and its dependencies in correct order."""

    # Get dependency tree
    deps = mcp__odoo - intelligence__addon_dependencies(addon_name=primary_module)

    # Calculate update order (dependencies first)
    update_order = calculate_dependency_order(deps)

    # Update in sequence
    for module in update_order:
        result = mcp__odoo - intelligence__odoo_update_module(modules=module)
        if "ERROR" in result:
            return {'success': False, 'failed_module': module, 'error': result}

    return {'success': True, 'updated_modules': update_order}
```

## Log Management Patterns

### Comprehensive Log Analysis

```python
def analyze_system_logs():
    """Analyze logs across all containers for issues."""

    # Get logs from all Odoo containers
    containers = mcp__docker__list_containers()
    odoo_containers = [c for c in containers if '${ODOO_PROJECT_NAME}' in c['Names'][0]]

    log_analysis = {}

    for container in odoo_containers:
        container_name = container['Names'][0]

        # Get recent logs
        logs = mcp__docker__fetch_container_logs(
            container_id=container['Id'],
            tail=500
        )

        # Analyze log content
        log_analysis[container_name] = {
            'error_count': logs.count('ERROR'),
            'warning_count': logs.count('WARNING'),
            'critical_count': logs.count('CRITICAL'),
            'recent_errors': extract_recent_errors(logs),
            'performance_issues': find_performance_issues(logs),
            'size_mb': len(logs.encode('utf-8')) / (1024 * 1024)
        }

    # Get Odoo-specific logs with more detail
    odoo_logs = mcp__odoo - intelligence__odoo_logs(lines=1000)
    log_analysis['odoo_detailed'] = analyze_odoo_logs(odoo_logs)

    return log_analysis


def extract_recent_errors(logs):
    """Extract and categorize recent errors."""
    lines = logs.split('\n')
    errors = []

    for i, line in enumerate(lines):
        if 'ERROR' in line or 'CRITICAL' in line:
            # Get context around error
            context_start = max(0, i - 2)
            context_end = min(len(lines), i + 3)
            context = '\n'.join(lines[context_start:context_end])

            errors.append({
                'timestamp': extract_timestamp(line),
                'message': line,
                'context': context,
                'category': categorize_error(line)
            })

    return errors[-10:]  # Return last 10 errors


def find_performance_issues(logs):
    """Identify performance-related log entries."""
    performance_patterns = [
        'slow query',
        'timeout',
        'memory',
        'performance',
        'took .* seconds',
        'deadlock'
    ]

    issues = []
    for line in logs.split('\n'):
        for pattern in performance_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append({
                    'line': line,
                    'pattern': pattern,
                    'severity': assess_performance_severity(line, pattern)
                })

    return issues
```

## Development Environment Patterns

### Development Workflow Support

```python
def setup_development_environment():
    """Prepare containers for development work."""

    # Ensure all containers are running
    health_check = comprehensive_container_health_check()

    if not all(c['State'] == 'running' for c in health_check['containers']):
        # Start missing containers
        for container in health_check['containers']:
            if container['State'] != 'running':
                mcp__docker__start_container(container_id=container['Id'])

    # Update modules to latest
    mcp__odoo - intelligence__odoo_update_module(modules="product_connect")

    # Clear any stale data
    clear_development_cache()

    return mcp__odoo - intelligence__odoo_status()


def development_module_cycle(module_name):
    """Complete development cycle: update -> test -> restart if needed."""

    # Update module
    update_result = mcp__odoo - intelligence__odoo_update_module(modules=module_name)

    # Check for errors that require restart
    needs_restart = any(keyword in update_result for keyword in [
        'ImportError',
        'SyntaxError',
        'NameError',
        'registry reload'
    ])

    if needs_restart:
        # Restart only necessary services
        mcp__odoo - intelligence__odoo_restart(services="web-1,shell-1")

        # Re-update after restart
        update_result = mcp__odoo - intelligence__odoo_update_module(modules=module_name)

    return {
        'update_result': update_result,
        'restart_performed': needs_restart,
        'final_status': mcp__odoo - intelligence__odoo_status()
    }
```

## Container Resource Management

### Resource Monitoring Patterns

```python
def monitor_container_resources():
    """Monitor container resource usage."""

    containers = mcp__docker__list_containers()
    resource_stats = {}

    for container in containers:
        if '${ODOO_PROJECT_NAME}' in container['Names'][0]:
            # Note: Would need additional Docker API access for full stats
            # This is a pattern for when that's available
            container_name = container['Names'][0]

            # Get basic info available through current tools
            logs = mcp__docker__fetch_container_logs(
                container_id=container['Id'],
                tail=50
            )

            resource_stats[container_name] = {
                'status': container['State'],
                'uptime': calculate_uptime(container['Created']),
                'log_size_indicator': len(logs),
                'recent_memory_warnings': logs.count('memory'),
                'recent_errors': logs.count('ERROR')
            }

    return resource_stats


def optimize_container_performance():
    """Optimize container performance based on current state."""

    # Check for containers with high error rates
    stats = monitor_container_resources()

    optimization_actions = []

    for container_name, stats_data in stats.items():
        if stats_data['recent_errors'] > 10:
            optimization_actions.append({
                'container': container_name,
                'action': 'restart',
                'reason': 'high_error_rate'
            })

        elif 'web' in container_name and stats_data['recent_memory_warnings'] > 5:
            optimization_actions.append({
                'container': container_name,
                'action': 'restart',
                'reason': 'memory_pressure'
            })

    # Execute optimization actions
    for action in optimization_actions:
        if action['action'] == 'restart':
            mcp__odoo - intelligence__odoo_restart(
                services=action['container'].replace('${ODOO_PROJECT_NAME}-', '').replace('-1', '')
            )

    return optimization_actions
```

## Network and Connectivity Patterns

### Network Troubleshooting

```python
def diagnose_network_issues():
    """Diagnose container networking problems."""

    # Check container connectivity
    containers = mcp__docker__list_containers()
    network_status = {}

    # Check if containers can reach each other
    for container in containers:
        if '${ODOO_PROJECT_NAME}' in container['Names'][0]:
            container_name = container['Names'][0]

            # Basic connectivity check through logs
            logs = mcp__docker__fetch_container_logs(
                container_id=container['Id'],
                tail=100
            )

            network_status[container_name] = {
                'connection_errors': logs.count('Connection refused'),
                'timeout_errors': logs.count('timeout'),
                'dns_errors': logs.count('Name resolution'),
                'status': container['State']
            }

    # Check external connectivity (Shopify API)
    external_connectivity = check_external_apis()

    return {
        'internal_network': network_status,
        'external_connectivity': external_connectivity
    }


def check_external_apis():
    """Check connectivity to external APIs."""

    # Look for API connection issues in logs
    odoo_logs = mcp__odoo - intelligence__odoo_logs(lines=200)

    api_status = {
        'shopify': {
            'connection_errors': odoo_logs.count('shopify.*connection'),
            'rate_limit_errors': odoo_logs.count('429'),
            'auth_errors': odoo_logs.count('401'),
            'timeout_errors': odoo_logs.count('shopify.*timeout')
        }
    }

    return api_status
```

## Backup and Recovery Patterns

### Container Data Management

```python
def create_container_backup():
    """Create backup of container data and configuration."""

    backup_info = {
        'timestamp': datetime.now().isoformat(),
        'containers': [],
        'volumes': []
    }

    # Get current container state
    containers = mcp__docker__list_containers()
    for container in containers:
        if '${ODOO_PROJECT_NAME}' in container['Names'][0]:
            backup_info['containers'].append({
                'name': container['Names'][0],
                'image': container['Image'],
                'state': container['State'],
                'created': container['Created']
            })

    # Get volume information
    volumes = mcp__docker__list_volumes()
    backup_info['volumes'] = volumes

    return backup_info


def disaster_recovery_procedure():
    """Emergency recovery procedure for complete failure."""

    recovery_steps = []

    # Step 1: Assess damage
    try:
        status = mcp__odoo - intelligence__odoo_status()
        recovery_steps.append("Status check: Partial failure")
    except:
        recovery_steps.append("Status check: Complete failure")

    # Step 2: Stop all containers
    try:
        containers = mcp__docker__list_containers()
        for container in containers:
            if '${ODOO_PROJECT_NAME}' in container['Names'][0]:
                mcp__docker__stop_container(container_id=container['Id'])
        recovery_steps.append("Stopped all containers")
    except Exception as e:
        recovery_steps.append(f"Container stop failed: {e}")

    # Step 3: Start in dependency order
    try:
        # Start database first
        db_containers = [c for c in containers if 'database' in c['Names'][0]]
        for container in db_containers:
            mcp__docker__start_container(container_id=container['Id'])

        time.sleep(20)  # Wait for database
        recovery_steps.append("Database container started")

        # Start application containers
        app_containers = [c for c in containers
                          if '${ODOO_PROJECT_NAME}' in c['Names'][0] and 'database' not in c['Names'][0]]
        for container in app_containers:
            mcp__docker__start_container(container_id=container['Id'])
            time.sleep(5)

        recovery_steps.append("Application containers started")

    except Exception as e:
        recovery_steps.append(f"Recovery failed: {e}")

    # Step 4: Verify recovery
    final_status = mcp__odoo - intelligence__odoo_status()
    recovery_steps.append(f"Final status: {final_status}")

    return {
        'recovery_steps': recovery_steps,
        'final_status': final_status,
        'success': 'healthy' in str(final_status)
    }
```

## Integration with Other Agents

### Coordination Patterns

```python
# Called by Owl agent after frontend changes
def restart_for_frontend_changes():
    """Restart containers to apply frontend changes."""

    # Only restart web container for frontend changes
    result = mcp__odoo - intelligence__odoo_restart(services="web-1")

    # Wait for restart to complete
    time.sleep(10)

    # Verify restart was successful
    status = mcp__odoo - intelligence__odoo_status()

    return {
        'restart_result': result,
        'current_status': status,
        'success': 'running' in str(status)
    }


# Called by Debugger agent for container diagnostics
def provide_debug_context(container_name=None):
    """Provide container context for debugging."""

    if container_name:
        # Specific container diagnostics
        containers = mcp__docker__list_containers()
        target = [c for c in containers if container_name in c['Names'][0]]

        if target:
            return {
                'container_info': target[0],
                'logs': mcp__docker__fetch_container_logs(
                    container_id=target[0]['Id'],
                    tail=200
                ),
                'status': target[0]['State']
            }
    else:
        # Full system diagnostics
        return comprehensive_container_health_check()


# Called by Scout agent for test environment setup
def prepare_test_environment():
    """Ensure containers are ready for testing."""

    # Make sure script-runner is available for tests
    containers = mcp__docker__list_containers()
    script_runner = [c for c in containers if 'script-runner' in c['Names'][0]]

    if not script_runner or script_runner[0]['State'] != 'running':
        mcp__docker__start_container(container_id=script_runner[0]['Id'])
        time.sleep(5)

    # Verify test database connectivity
    test_db_check = mcp__odoo - intelligence__odoo_status()

    return {
        'script_runner_ready': bool(script_runner),
        'database_ready': 'database' in str(test_db_check),
        'overall_ready': 'healthy' in str(test_db_check)
    }
```

## Performance Optimization Patterns

### Container Performance Tuning

```python
def optimize_container_configuration():
    """Analyze and optimize container performance."""

    # Analyze current performance
    perf_data = monitor_container_resources()

    optimization_recommendations = []

    # Check for containers with performance issues
    for container_name, stats in perf_data.items():
        if stats['recent_errors'] > 20:
            optimization_recommendations.append({
                'container': container_name,
                'issue': 'high_error_rate',
                'recommendation': 'Consider restart or configuration review',
                'priority': 'high'
            })

        if stats['recent_memory_warnings'] > 10:
            optimization_recommendations.append({
                'container': container_name,
                'issue': 'memory_pressure',
                'recommendation': 'Monitor memory usage, consider optimization',
                'priority': 'medium'
            })

    return {
        'current_performance': perf_data,
        'recommendations': optimization_recommendations,
        'optimization_available': len(optimization_recommendations) > 0
    }


def clean_container_environment():
    """Clean up container environment for optimal performance."""

    cleanup_actions = []

    # Clear old logs (conceptual - would need log rotation setup)
    containers = mcp__docker__list_containers()
    for container in containers:
        if '${ODOO_PROJECT_NAME}' in container['Names'][0]:
            logs = mcp__docker__fetch_container_logs(
                container_id=container['Id'],
                tail=10
            )

            # If logs are very large, recommend log rotation
            if len(logs) > 100000:  # Rough estimate
                cleanup_actions.append({
                    'container': container['Names'][0],
                    'action': 'log_rotation_needed',
                    'size_estimate': 'large'
                })

    return cleanup_actions
```
