# Environment Banner Context

Shared backend banner for non-production environments.

## Key Files

- `static/src/js/environment_banner.js`
- `static/src/xml/environment_banner.xml`
- `static/src/scss/environment_banner.scss`
- `models/ir_http.py` (session_info config injection)

## Configuration

- `environment_banner.enabled` (default True)
- `environment_banner.production_hostnames` (comma or whitespace-separated hostnames)

## References

- @docs/policies/coding-standards.md
- @docs/style/javascript.md
