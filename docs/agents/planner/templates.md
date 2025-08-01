# Planner Templates

## New Model Planning Template

```yaml
Model Planning:
  Definition:
    - Model name and purpose
    - Fields and types
    - Constraints and validation
    - Computed fields with dependencies
    - Related fields
    
  Business Logic:
    - CRUD method overrides
    - Custom actions
    - Workflow states
    - Button methods
    
  Integration:
    - Related model updates
    - External API sync points
    - Event triggers
    
  UI/UX:
    - Form view layout
    - List view columns
    - Search filters
    - Menu structure
    
  Testing:
    - Unit test scenarios
    - Integration test flows
    - Tour test paths
```

## Feature Planning Examples

### Product Bundle Feature

```python
# 1. Analyze existing structure
product_info = mcp__odoo-intelligence__model_info(model_name="product.template")
bundle_examples = mcp__odoo-intelligence__search_models(pattern="bundle|kit")

# 2. Create implementation tasks
TodoWrite([
    {"content": "Create product.bundle model", "priority": "high"},
    {"content": "Add bundle_line_ids to product.template", "priority": "high"},
    {"content": "Create bundle pricing logic", "priority": "high"},
    {"content": "Design bundle management views", "priority": "medium"},
    {"content": "Update inventory calculations", "priority": "medium"},
    {"content": "Create bundle tests", "priority": "medium"}
])
```

### Motor Compatibility Matrix

```python
# 1. Current structure analysis
motor_info = mcp__odoo-intelligence__model_info(model_name="motor.product")
relationships = mcp__odoo-intelligence__model_relationships(model_name="motor.product")

# 2. Design decisions
"""
Schema Design:
- motor.compatibility (M2M through model)
- Fields: motor_id, compatible_motor_id, compatibility_type
- Bidirectional compatibility checking
- Views: Tree/form for management
"""
```

### Shipping Integration

```python
# 1. Research existing patterns
shipping_models = mcp__odoo-intelligence__search_models(pattern="shipping|delivery")
integration_patterns = mcp__odoo-intelligence__search_code(
    pattern="class.*Integration|service.*api",
    file_type="py"
)

# 2. Architecture layers
"""
Integration Architecture:
1. Abstract base service class
2. API-specific implementation  
3. Error handling and retry logic
4. Configuration management
5. Mock testing support
"""
```

## Performance Planning

### Database Optimization
- Identify high-traffic tables
- Plan indexing strategy
- Design denormalization if needed
- Plan batch operations

### Caching Strategy
- What data to cache
- Cache invalidation rules
- Memory usage planning
- Redis vs in-memory

## Security Planning

### Access Control Design
```python
"""
User Groups:
- product_connect.group_user - Basic access
- product_connect.group_manager - Full access

Record Rules:
- Company-based isolation
- State-based visibility
- Owner-based editing
"""
```

### Data Validation
- Input sanitization points
- Business rule enforcement
- Audit trail requirements