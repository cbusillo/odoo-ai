# 📦 Odoo Feature Development Workflow

## Complete Development Pattern

**As PM, coordinate this workflow:**

1. **Research** → Archer finds Odoo patterns and examples
2. **Plan** → Break into models/views/tests/security components
3. **Parallel Implementation**:
    - Models → Appropriate agent (domain specialist)
    - Frontend → Owl (Owl.js expertise)
    - Tests → Scout (test patterns)
    - Security → Inspector (access rules)
4. **Integration** → Inspector validates code quality
5. **Deployment** → Dock updates module in containers

## Critical Post-Development Steps

**After code changes**: Always update module with `mcp__odoo-intelligence__odoo_update_module`

**Quality Gates**:

- Inspector runs full code analysis
- Scout verifies test coverage
- QC agent validates overall quality

## Architecture Patterns

**Addons**: `product_connect` (core), `disable_odoo_online`  
**Key Paths**: `./addons` (custom), Database: `${ODOO_DB_NAME}`  
**DO NOT MODIFY**: `services/shopify/gql/*` (generated), `graphql/schema/*`

## Research Resources

**Detailed Architecture**: See [@docs/agents/archer.md](agents/archer.md) for research patterns
**Implementation Details**: See [ARCHITECTURE.md](ARCHITECTURE.md)

---
[← Back to Main Guide](/CLAUDE.md)
