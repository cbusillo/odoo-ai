---
title: External Resources
---

Purpose

- Provide external documentation and API references for the stack.
- For project-specific docs, start with [docs/README.md](README.md).

When

- When you need canonical external references.

## External Documentation

### Odoo 19 Enterprise

**Website**: [Odoo 19 Documentation](https://www.odoo.com/documentation/19.0/)

Key sections for development:

- **Developer Guide**:
  [Odoo Developer Documentation](https://www.odoo.com/documentation/19.0/developer.html)
- **ORM Reference**:
  [ORM Reference](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html)
- **View Architecture**:
  [View Architecture](https://www.odoo.com/documentation/19.0/developer/reference/user_interface/view_architectures.html)
- **Frontend Framework**:
  [Frontend Framework](https://www.odoo.com/documentation/19.0/developer/reference/frontend.html)
- **Applications Guide**:
  [Applications Guide](https://www.odoo.com/documentation/19.0/applications.html)

### Shopify GraphQL API

**Website**:
[Shopify Admin GraphQL API](https://shopify.dev/docs/api/admin-graphql)
**Local schema**: `addons/shopify_sync/graphql/schema/shopify_schema_2026-01.sdl`

Use the local schema file for complete type definitions and the online docs for
guides and best practices.

### PostgreSQL

**Website**: [PostgreSQL Documentation](https://www.postgresql.org/docs/)
**Note**: Basic SQL usage only

### Python

**Website**: [Python Documentation](https://docs.python.org/)

### Docker Compose

**Website**: [Docker Compose Documentation](https://docs.docker.com/compose/)

### Other Technologies in Stack

**Pydantic** - [Docs](https://docs.pydantic.dev/latest/)

**httpx** - [Docs](https://www.python-httpx.org/)

**Owl.js** - [Repository](https://github.com/odoo/owl)

**ariadne-codegen** - [Docs](https://ariadnegraphql.org/client/intro)

- GraphQL code generator (you generate from schema, docs rarely needed)

## Quick Reference Commands

```bash
# Check your package versions
grep -r "from pydantic" addons/shopify_sync/
grep -r "import httpx" addons/shopify_sync/

# Check modern Python features in use
# (See `pyproject.toml` → `requires-python` for the baseline.)
grep -r "type \|match \|case " addons/shopify_sync/

# Check PostgreSQL version
docker exec ${ODOO_PROJECT_NAME}-database-1 psql -U odoo -c "SELECT version();"

# Search Shopify schema for specific types
grep -A10 "^type Product" addons/shopify_sync/graphql/schema/shopify_schema_2026-01.sdl
```
