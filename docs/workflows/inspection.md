Title: Inspection Workflows

Systematic workflows for code inspection and quality assessment.

## Inspection Process Patterns

### Full Project Inspection
```bash
# Trigger comprehensive inspection
inspection_trigger()

# Monitor progress
inspection_get_status()

# Retrieve results when complete
inspection_get_problems(scope="whole_project", severity="all")
```

### Targeted Inspections
```bash
# Focus on specific areas
inspection_get_problems(
    scope="custom_scope", 
    file_pattern="*.py",
    problem_type="PyUnresolvedReferencesInspection"
)
```

### Severity-based Workflows
```bash
# Critical issues first
inspection_get_problems(severity="error", limit=50)

# Then warnings
inspection_get_problems(severity="warning", limit=100)

# Finally low-priority items
inspection_get_problems(severity="weak_warning", limit=200)
```

## Inspection Automation Patterns

### Continuous Inspection
- Schedule regular full project scans
- Monitor inspection status automatically
- Alert on new critical issues
- Track quality metrics over time

### Branch-specific Inspection
- Inspect changes in feature branches
- Compare quality metrics with main branch
- Gate merges on quality thresholds
- Document quality improvements

### Module-focused Inspection
- Target specific Odoo modules
- Validate custom addon quality
- Check integration points
- Verify migration compatibility

## Result Processing Patterns

### Issue Categorization
```python
def categorize_issues(problems):
    categories = {
        'security': [],
        'performance': [],
        'maintainability': [],
        'style': []
    }
    
    for problem in problems:
        if 'security' in problem.type.lower():
            categories['security'].append(problem)
        elif 'performance' in problem.type.lower():
            categories['performance'].append(problem)
        # ... continue categorization
    
    return categories
```

### Priority Assignment
```python
def assign_priority(problem):
    if problem.severity == 'error':
        return 'critical'
    elif 'security' in problem.type.lower():
        return 'high'
    elif problem.severity == 'warning':
        return 'medium'
    else:
        return 'low'
```

## Workflow Integration

### With Quality Control
1. Inspector identifies issues
2. QC agent triages and prioritizes
3. Appropriate agents handle fixes
4. Inspector validates corrections

### With Development Workflow
1. Pre-commit inspection for new code
2. Branch inspection before merge
3. Release inspection for quality gates
4. Post-deployment monitoring

### With Documentation
1. Generate quality reports
2. Track improvement metrics
3. Document recurring patterns
4. Maintain quality standards

## Inspection Reporting

### Summary Reports
- Issue count by severity
- Top problem types
- Quality trend analysis
- Module-specific metrics

### Detailed Analysis
- File-by-file breakdown
- Pattern occurrence frequency
- Resolution time tracking
- Quality improvement suggestions

### Actionable Outputs
- Prioritized fix lists
- Agent assignment recommendations
- Quality gate compliance status
- Next inspection scheduling
