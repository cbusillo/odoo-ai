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

## Project Command Routing

- For local runtime and deploy commands, start with
  [@docs/tooling/platform-cli.md](tooling/platform-cli.md).
- For test and gate commands, use [@docs/TESTING.md](TESTING.md) and
  [@docs/tooling/testing-cli.md](tooling/testing-cli.md).
- For Docker and Compose troubleshooting, use
  [@docs/tooling/docker.md](tooling/docker.md).
