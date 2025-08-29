# External Resources

This document provides links to external documentation and API references for the technologies used in this project.

**For project-specific documentation, see [CLAUDE.md](../CLAUDE.md).**

## External Documentation

### Odoo 18 Enterprise

**Website**: https://www.odoo.com/documentation/18.0/
**Your version**: 18.0 Enterprise

Key sections for development:

- **Developer Documentation**: https://www.odoo.com/documentation/18.0/developer.html
    - ORM Reference: https://www.odoo.com/documentation/18.0/developer/reference/backend/orm.html
    - View
      Architecture: https://www.odoo.com/documentation/18.0/developer/reference/user_interface/view_architectures.html
    - Frontend Framework: https://www.odoo.com/documentation/18.0/developer/reference/frontend.html
- **Applications**: https://www.odoo.com/documentation/18.0/applications.html

### Shopify GraphQL API

**Website**: https://shopify.dev/docs/api/admin-graphql
**Your version**: 2025-04 (latest stable)
**Local schema**: `addons/product_connect/graphql/schema/shopify_schema_2025-04.sdl` (61k+ lines)

Use the local schema file for complete type definitions and the online docs for guides and best practices.

### PostgreSQL 17

**Website**: https://www.postgresql.org/docs/17/
**Your version**: 17 (latest)
**Note**: Basic SQL usage only, comprehensive docs probably not needed

### Python 3.12+

**Website**: https://docs.python.org/3.12/
**Your version**: 3.12+
**Note**: In Claude's training data ✓

### Docker Compose

**Website**: https://docs.docker.com/compose/
**Your version**: v2
**Note**: In Claude's training data ✓

### Other Technologies in Stack

**Pydantic v2** - https://docs.pydantic.dev/latest/

- Your version: v2 (in Claude's training ✓)

**httpx** - https://www.python-httpx.org/

- HTTP client library (in Claude's training ✓)

**Owl.js 2.0** - https://github.com/odoo/owl

- Frontend framework (covered in Odoo docs)

**ariadne-codegen** - https://ariadne-codegen.readthedocs.io/

- GraphQL code generator (you generate from schema, docs rarely needed)

## Quick Reference Commands

```bash
# Check your package versions
grep -r "from pydantic" addons/product_connect/
grep -r "import httpx" addons/product_connect/

# Check Python 3.12+ features in use
grep -r "type \|match \|case " addons/product_connect/

# Check PostgreSQL version
docker exec ${ODOO_PROJECT_NAME}-database-1 psql -U odoo -c "SELECT version();"

# Search Shopify schema for specific types
grep -A10 "^type Product" addons/product_connect/graphql/schema/shopify_schema_2025-04.sdl
```
