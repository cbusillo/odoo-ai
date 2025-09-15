# Docker MCP Usage Notes

This project uses the Docker MCP server (`mcp-server-docker`) for container operations. Some client wrappers flatten
complex parameters to string fields. When invoking these tools, pass JSON-encoded objects/lists for any structured
arguments.

## Quick Rules

- `environment` → JSON object or array of `KEY=VALUE` strings
- `ports` → JSON object mapping container port (e.g., `"5432/tcp"`) → host binding
- `volumes` → JSON object mapping host path or named volume → `{ "bind": "/container/path", "mode": "rw" }`

## Examples

- Run Postgres:
    - tool: `run_container`
    - image: `"postgres:17"`
    - name: `"odoo-ci-db"`
    - environment: `{ "POSTGRES_DB": "postgres", "POSTGRES_USER": "odoo", "POSTGRES_PASSWORD": "odoo" }`
    - ports: `{ "5432/tcp": 54322 }`

- Create a network:
    - tool: `create_network`
    - name: `"odoo-ci"`

- Exec in an existing service (compose-created):
    - Prefer `docker compose exec -T <service> ...` via `tools/testkit/docker_api.py` helpers when running project
      tests.

## Why JSON Strings?

Some clients expose these parameters as strings. Provide valid JSON text for those fields, which the server parses into
Docker SDK shapes. If you pass raw text (e.g., `"54322:5432"` or newline env), validation fails with “not valid under
any schema.”

## Troubleshooting

- Validate connectivity with `list_containers` first. If it returns data, the server is healthy.
- For parameter shape errors, convert complex fields to JSON objects/lists per the rules above.
- On macOS, ensure the Docker socket is available to the server if running in a container.

## References

- Package: `mcp-server-docker` on PyPI
- Docker SDK parameter shapes: environment, ports, volumes

