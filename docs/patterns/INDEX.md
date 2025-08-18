# Pattern Library Index

## Quick Navigation

This index provides centralized access to all pattern documentation in the project.

## Core Patterns

### Odoo 18 Patterns
- [API Patterns](../odoo18/API_PATTERNS.md) - New decorators, field types, ORM improvements
- [Advanced Testing](../odoo18/TESTING_ADVANCED.md) - Computed fields, cache, security testing
- [Security Patterns](../odoo18/SECURITY_PATTERNS.md) - Access rights, sudo usage, multi-company
- [Performance ORM](../odoo18/PERFORMANCE_ORM.md) - Query optimization, indexing, batch processing

### Agent Patterns

#### Development Patterns
- [Scout Scenarios](../agent-patterns/scout-common-scenarios.md) - Test writing patterns
- [Refactor Workflows](../agent-patterns/refactor-workflows.md) - Safe refactoring processes
- [Refactor Safety](../agent-patterns/refactor-safety-checks.md) - Pre-refactor validation

#### Framework Patterns
- [Odoo Engineer](../agent-patterns/odoo-engineer-patterns.md) - Framework best practices
- [Anthropic Patterns](../agent-patterns/anthropic-patterns.md) - Claude optimization
- [Phoenix Migration](../agent-patterns/phoenix-patterns.md) - Version migration patterns

#### Frontend Patterns
- [Owl Components](../agent-patterns/component-patterns.md) - Owl.js 2.0 patterns
- [Owl Troubleshooting](../agent-patterns/owl-troubleshooting.md) - Common frontend issues
- [Hoot Testing](../agent-patterns/hoot-testing.md) - JavaScript test patterns

#### Testing Patterns
- [Test Templates](../agent-patterns/test-templates.md) - Reusable test structures
- [Tour Patterns](../agent-patterns/tour-patterns.md) - Browser tour testing
- [Tour Debugging](../agent-patterns/tour-debugging.md) - Tour test troubleshooting
- [Playwright Patterns](../agent-patterns/playwright-patterns.md) - Browser automation
- [Playwright Selectors](../agent-patterns/playwright-selectors.md) - Element selection

#### Quality & Performance
- [QC Patterns](../agent-patterns/qc-patterns.md) - Quality control coordination
- [Flash Patterns](../agent-patterns/flash-patterns.md) - Performance analysis
- [Inspection Workflows](../agent-patterns/inspection-workflows.md) - Code inspection

#### Integration Patterns
- [Shopify Sync](../agent-patterns/sync-patterns.md) - Shopify synchronization
- [GraphQL Patterns](../agent-patterns/graphql-patterns.md) - GraphQL operations
- [Webhook Patterns](../agent-patterns/webhook-patterns.md) - Webhook handling
- [Service Patterns](../agent-patterns/service-patterns.md) - Service layer design

#### Infrastructure Patterns
- [Docker Patterns](../agent-patterns/dock-patterns.md) - Container operations
- [Bulk Operations](../agent-patterns/bulk-operations.md) - Mass data processing

#### Planning & Documentation
- [Planner Templates](../agent-patterns/planner-templates.md) - Task planning
- [Doc Patterns](../agent-patterns/doc-patterns.md) - Documentation maintenance

#### Research & Discovery
- [Odoo Core Research](../agent-patterns/odoo-core-research.md) - Framework exploration

#### Session Management
- [GPT Session Patterns](../agent-patterns/gpt-session-patterns.md) - Session optimization
- [GPT Performance](../agent-patterns/gpt-performance-patterns.md) - GPT optimization

#### Migration & Compatibility

## Quick Reference by Task

### When Writing Code
1. Check [API Patterns](../odoo18/API_PATTERNS.md) for Odoo 18 features
2. Review [Security Patterns](../odoo18/SECURITY_PATTERNS.md) for access control
3. Apply [Performance ORM](../odoo18/PERFORMANCE_ORM.md) for optimization

### When Testing
1. Start with [Test Templates](../agent-patterns/test-templates.md)
2. Use [Advanced Testing](../odoo18/TESTING_ADVANCED.md) for complex scenarios
3. Debug with [Tour Debugging](../agent-patterns/tour-debugging.md)

### When Debugging
1. Use debugger agent for error investigation
2. Check dock agent for Docker issues
3. Use flash agent for performance issues

### When Refactoring
1. Start with [Refactor Safety](../agent-patterns/refactor-safety-checks.md)
2. Follow [Refactor Workflows](../agent-patterns/refactor-workflows.md)
3. Use [Bulk Operations](../agent-patterns/bulk-operations.md) for large changes

### When Integrating
1. Review [Service Patterns](../agent-patterns/service-patterns.md)
2. Implement [GraphQL Patterns](../agent-patterns/graphql-patterns.md)
3. Handle [Webhook Patterns](../agent-patterns/webhook-patterns.md)

## Pattern Categories

### By Complexity
- **Basic**: Test Templates, Component Patterns, Doc Patterns
- **Intermediate**: Service Patterns, Refactor Workflows, Quality Patterns
- **Advanced**: Performance ORM, Security Patterns, Migration Patterns

### By Frequency
- **Daily Use**: API Patterns, Test Templates, Debugger Analysis
- **Weekly Use**: Refactor Workflows, Quality Patterns, Performance Debugging
- **Occasional**: Migration Patterns, Architecture Planning, Framework Migration

### By Domain
- **Backend**: API Patterns, ORM Performance, Security Patterns
- **Frontend**: Owl Components, Hoot Testing, UI Automation
- **Integration**: GraphQL, Webhooks, Shopify Sync
- **Infrastructure**: Docker, Container Management, Service Orchestration
- **Quality**: Inspection, QC Patterns, Pre-commit Quality

## Contributing

When adding new patterns:
1. Place in appropriate subdirectory (`odoo18/`, `agent-patterns/`)
2. Update this index with proper categorization
3. Include practical examples from product_connect
4. Cross-reference related patterns
5. Test all code examples

## Need Help?

- **Can't find a pattern?** Ask archer agent for research
- **Pattern unclear?** Use [Doc Patterns](../agent-patterns/doc-patterns.md)
- **Need examples?** Look in [Scout Scenarios](../agent-patterns/scout-common-scenarios.md)