# 🏗️ Odoo Architecture

This document outlines the architecture and structure of an Odoo 18 Enterprise deployment.

## 🎯 Project Overview

**Purpose**: Custom Odoo implementation for motor parts management with Shopify integration  
**Stack**: Python 3.12+, PostgreSQL 17, Owl.js 2.0, Docker, GraphQL  
**Database**: `${ODOO_DB_NAME}`

## 📁 Directory Structure

### Root Level

```
/odoo-ai/
├── addons/                 # Custom addons (accessible from host)
├── docs/                   # Documentation
├── tools/                  # Development utilities
├── .claude/               # Claude Code configuration
├── docker-compose.yml     # Container orchestration
└── CLAUDE.md             # Main development guide
```

### Custom Addons Structure

```
addons/
├── product_connect/       # Core business addon
│   ├── models/           # Odoo models with inheritance
│   ├── static/src/js/    # Owl.js 2.0 components
│   ├── services/         # External integrations
│   ├── views/           # XML view definitions
│   ├── tests/           # Comprehensive test suite
│   └── __manifest__.py  # Addon metadata
└── disable_odoo_online/  # Utility addon
```

### Product Connect Internal Structure

```
addons/product_connect/
├── models/
│   ├── __init__.py           # Model imports
│   ├── product_template.py   # Main product model extensions
│   ├── motor.py             # Motor-specific functionality
│   ├── res_partner.py       # Customer extensions
│   └── sale_order.py        # Order processing
├── static/src/js/
│   ├── components/          # Reusable Owl components
│   ├── widgets/            # Field widgets
│   ├── views/              # Custom view types
│   └── services/           # Frontend services
├── services/
│   ├── shopify/            # Shopify integration
│   │   ├── client.py       # GraphQL client
│   │   ├── sync/           # Synchronization logic
│   │   └── gql/            # Generated GraphQL files ⚠️
│   └── __init__.py
├── tests/
│   ├── fixtures/           # Test base classes
│   ├── test_model_*.py     # Model tests
│   ├── test_service_*.py   # Service tests
│   └── static/tests/       # JavaScript tests
└── views/
    ├── product_template_views.xml
    ├── motor_views.xml
    └── menu_views.xml
```

## 🐳 Container Architecture

### Container Purposes
	
- **${ODOO_CONTAINER_PREFIX}-web-1**: Main web server (user requests)
- **${ODOO_CONTAINER_PREFIX}-shell-1**: Interactive shell operations
- **${ODOO_CONTAINER_PREFIX}-script-runner-1**: Module updates, tests, one-off scripts
- **${ODOO_CONTAINER_PREFIX}-database-1**: PostgreSQL database

### Container Paths (READ-ONLY)

**CRITICAL**: These paths exist INSIDE Docker containers only!

- `/odoo/addons/*` - Odoo Community core modules
- `/volumes/enterprise/*` - Odoo Enterprise modules
- `/volumes/addons/*` - Custom addons (mapped to `./addons`)
- `/volumes/data/*` - Filestore data

### Path Access Rules
	
- ✅ **Custom addons**: Use `Read("addons/product_connect/...")`
- ✅ **Odoo core**: Use `docker exec ${ODOO_CONTAINER_PREFIX}-web-1 cat /odoo/addons/...`
- ❌ **NEVER**: Use `Read("/odoo/...")` - path doesn't exist on host!

## 🧩 Component Architecture

### Models Layer

**Location**: `addons/product_connect/models/`

- **Inheritance Pattern**: Extends existing Odoo models using `_inherit`
- **Mixins**: Shared functionality across models
- **Custom Models**: New models specific to motor parts business

```python
# Example: Product Template Extension
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    motor_year = fields.Integer()
    motor_make = fields.Char()
    motor_model = fields.Char()
```

### Frontend Layer

**Location**: `addons/product_connect/static/src/js/`

- **Framework**: Owl.js 2.0 (modern JavaScript, NO jQuery)
- **Components**: Reusable UI elements
- **Views**: Custom view types (graphs, forms)
- **Widgets**: Specialized field controls

### Services Layer

**Location**: `addons/product_connect/services/`

- **Shopify Integration**: GraphQL-based synchronization
- **External APIs**: Third-party service connections
- **Data Processing**: Business logic services

### Views Layer

**Location**: `addons/product_connect/views/`

- **XML Definitions**: Odoo view configurations
- **Inheritance**: Extends existing views
- **Custom Views**: New view types for motor parts

## 🔄 Data Flow Architecture

### Shopify Integration Flow

```
Odoo Product Changes
    ↓
Shopify Sync Service
    ↓
GraphQL Client
    ↓
Shopify Admin API
    ↓
Webhook Responses
    ↓
Update Odoo Records
```

### Motor Parts Workflow

```
Raw Product Data
    ↓
Motor Classification
    ↓
Compatibility Matching
    ↓
Inventory Management
    ↓
Shopify Export
    ↓
Customer Orders
```

## 🚫 DO NOT MODIFY

**Generated Files** (auto-generated, will be overwritten):

- `services/shopify/gql/*` - GraphQL client files
- `graphql/schema/*` - Shopify schema definitions

**Core Odoo Files** (container-only paths):

- `/odoo/addons/*` - Odoo community source
- `/volumes/enterprise/*` - Enterprise modules

## 🧪 Testing Architecture

### Test Structure

```
tests/
├── fixtures/
│   ├── test_base.py          # Base test classes
│   └── test_service_utils.py # Service test helpers
├── test_model_*.py           # Model unit tests
├── test_service_*.py         # Service integration tests
├── test_tour_*.py           # UI tour runners
└── static/tests/
    ├── *.test.js            # JavaScript unit tests (Hoot)
    └── tours/               # Tour definitions
```

### Test Data Strategy

- **Base Classes**: Pre-configured test data in fixtures
- **SKU Validation**: 4-8 digit numeric SKUs for consumables
- **Context Flags**: `skip_shopify_sync=True` in test environment
- **Mocking**: External API calls mocked at class level

## 🔧 Development Patterns

### Model Extensions

```python
# Standard inheritance pattern
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Add fields
    custom_field = fields.Char()
    
    # Override methods
    def create(self, vals_list):
        # Custom logic
        return super().create(vals_list)
```

### Frontend Components

```javascript
// Owl.js 2.0 component pattern
import { Component } from "@odoo/owl";

export class CustomWidget extends Component {
    static template = "product_connect.CustomWidget";
    static props = ["*"];
    
    setup() {
        // Component setup
    }
}
```

### Service Integration

```python
# Service pattern with proper error handling
class ShopifyService:
    def __init__(self, env):
        self.env = env
        self.client = ShopifyClient()
    
    def sync_product(self, product):
        try:
            result = self.client.execute(query, variables)
            return self._process_result(result)
        except ShopifyError as e:
            _logger.error(f"Shopify sync failed: {e}")
            raise
```

## 📊 Performance Considerations

### Database Optimization

- **Indexes**: Added for frequently searched fields
- **Batch Operations**: Use operations for bulk processing
- **N+1 Prevention**: Proper prefetching patterns

### Frontend Optimization

- **Component Lifecycle**: Proper setup/cleanup
- **Event Handling**: Efficient listener management
- **Asset Loading**: Optimized JavaScript bundling

### API Integration

- **Rate Limiting**: Respect Shopify API limits
- **Caching**: Cache expensive operations
- **Error Recovery**: Robust retry mechanisms

## 🔗 External Dependencies

### Python Packages

- Standard Odoo dependencies
- GraphQL client libraries
- Testing frameworks (unittest, mock)

### JavaScript Dependencies

- Owl.js 2.0 framework
- Odoo web framework components
- Hoot testing framework

### System Dependencies

- PostgreSQL 17
- Docker & Docker Compose
- Ruff for code formatting

## 🔐 Security Architecture

### Access Control

- **Odoo Groups**: Fine-grained permission system
- **Record Rules**: Row-level security
- **Field-Level**: Sensitive data protection

### API Security

- **Authentication**: Shopify webhook validation
- **Rate Limiting**: Prevent abuse
- **Data Validation**: Input sanitization

### Development Security

- **No Secrets**: Never commit API keys or tokens
- **Environment Variables**: Secure configuration management
- **Code Review**: Security-focused review process

## 📈 Scalability Design

### Database Scaling

- **Partitioning**: Large table optimization
- **Connection Pooling**: Efficient database usage
- **Query Optimization**: Performance monitoring

### Application Scaling

- **Stateless Design**: Container-friendly architecture
- **Caching Strategy**: Redis integration ready
- **Queue Processing**: Background job handling

### Integration Scaling

- **Webhook Processing**: Async handling
- **Batch Synchronization**: Bulk operations
- **Error Recovery**: Resilient retry logic

## 🎯 Best Practices

### Code Organization

- **Single Responsibility**: Each module has clear purpose
- **Loose Coupling**: Minimal inter-module dependencies
- **High Cohesion**: Related functionality grouped together

### Development Workflow

1. **Research**: Use Archer agent for Odoo patterns
2. **Plan**: Use Planner agent for complex features
3. **Implement**: Follow existing patterns
4. **Test**: Use Scout agent for comprehensive tests
5. **Review**: Use Inspector agent for quality checks

### Documentation

- **Self-Documenting Code**: Clear naming, minimal comments
- **API Documentation**: Service interfaces documented
- **Architecture Decisions**: Recorded in docs/

This architecture supports the motor parts business requirements while maintaining Odoo best practices and scalability
for future growth.

## 📦 Order Management Strategy

### Import-Only Architecture

**Current Design**: Orders imported from external platforms (Shopify, eBay) for visibility only.

```
External Platform Orders
    ↓
Import via API
    ↓
Create Draft Orders (no confirmation)
    ↓
Reporting & Analytics
    ↓
External Fulfillment (source of truth)
```

### Key Decisions

- **Orders stay in draft**: Prevents inventory movements and stock impacts
- **External systems authoritative**: Inventory managed outside Odoo
- **Visibility focus**: Orders imported for reporting across platforms
- **Easy re-import**: Draft orders can be deleted/reimported during testing

### Implementation Notes

```python
# Orders marked with source platform
order.source_platform = 'shopify'  # or 'ebay', 'manual'

# Shipping captured separately
order.shipping_charge = 29.99

# Delivery mapping via service map
carrier_map = env['delivery.carrier.service.map']
```

### Future Migration Path

When Odoo becomes source of truth:
1. Enable order confirmation workflow
2. Implement bi-directional fulfillment sync
3. Activate inventory movements
4. Sync tracking information

## 🔒 Field Constraints and Inheritance

### Challenge: Required Fields in Inherited Models

When adding required fields to widely-inherited models, external modules can fail:

```
null value in column "source" violates not-null constraint
```

### Root Cause

- XML data imports bypass Python defaults
- External modules (delivery_ups_rest) create records via XML
- Our required fields unknown to external modules

### Solution Pattern

```python
# Make field optional at DB level, enforce in logic
source = fields.Selection(
    selection=[
        ("import", "Import Product"),
        ("motor", "Motor Product"),
        ("standard", "Standard Product")
    ],
    default="standard",
    required=False,  # Not required at DB level
    index=True,
)

# Add targeted SQL constraint
_sql_constraints = [
    ('source_required_for_consumables',
     "CHECK((type != 'consu') OR (source IS NOT NULL))",
     "Source is required for consumable products"),
]
```

### Best Practices

1. **Avoid strict constraints** on widely-inherited models
2. **Use SQL CHECK** constraints for conditional requirements
3. **Test with external modules** that create records
4. **Document special handling** for inherited fields
