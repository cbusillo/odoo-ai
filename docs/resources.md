---
title: External Resources
---


This document provides links to external documentation and API references for the technologies used in this project.

**For project-specific documentation, see [docs/README.md](README.md).**

## External Documentation

### Odoo 18 Enterprise

**Website**: https://www.odoo.com/documentation/18.0/

Key sections for development:

- **Developer Documentation**: https://www.odoo.com/documentation/18.0/developer.html
    - ORM Reference: https://www.odoo.com/documentation/18.0/developer/reference/backend/orm.html
    - View
      Architecture: https://www.odoo.com/documentation/18.0/developer/reference/user_interface/view_architectures.html
    - Frontend Framework: https://www.odoo.com/documentation/18.0/developer/reference/frontend.html
- **Applications**: https://www.odoo.com/documentation/18.0/applications.html

### Shopify GraphQL API

**Website**: https://shopify.dev/docs/api/admin-graphql
**Local schema**: `addons/product_connect/graphql/schema/shopify_schema_2025-04.sdl`

Use the local schema file for complete type definitions and the online docs for guides and best practices.

### PostgreSQL

**Website**: https://www.postgresql.org/docs/
**Note**: Basic SQL usage only

### Python

**Website**: https://docs.python.org/

### Docker Compose

**Website**: https://docs.docker.com/compose/

### Other Technologies in Stack

**Pydantic** - https://docs.pydantic.dev/latest/

**httpx** - https://www.python-httpx.org/

**Owl.js** - https://github.com/odoo/owl

**ariadne-codegen** - https://ariadne-codegen.readthedocs.io/

- GraphQL code generator (you generate from schema, docs rarely needed)

## Quick Reference Commands

```bash
# Check your package versions
grep -r "from pydantic" addons/product_connect/
grep -r "import httpx" addons/product_connect/

# Check modern Python features in use
# (See `pyproject.toml` → `requires-python` for the baseline.)
grep -r "type \|match \|case " addons/product_connect/

# Check PostgreSQL version
docker exec ${ODOO_PROJECT_NAME}-database-1 psql -U odoo -c "SELECT version();"

# Search Shopify schema for specific types
grep -A10 "^type Product" addons/product_connect/graphql/schema/shopify_schema_2025-04.sdl
```
