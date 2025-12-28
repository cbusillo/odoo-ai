# GPT Service Users

## Purpose

- Provide deterministic service accounts for GPT/Codex automation against local Odoo instances restored from upstream
  snapshots.

## Provisioning

- Restore runs seed or update both users whenever `ODOO_KEY` is defined in the environment.
- Each account receives a dedicated `res.partner` record, is flagged as non-share, and is attached to the first
  company (ordered by `id`).
- Login passwords and API keys are derived deterministically from `ODOO_KEY`, with API keys stored in
  `res.users.apikeys` and scoped for RPC access.

## Accounts

| Login       | Display Name     | Password   | API Key Plaintext  | Groups                                 |
|-------------|------------------|------------|--------------------|----------------------------------------|
| `gpt`       | GPT Service User | `ODOO_KEY` | `ODOO_KEY`         | `base.group_user`                      |
| `gpt-admin` | GPT Admin User   | `ODOO_KEY` | `admin-<ODOO_KEY>` | `base.group_user`, `base.group_system` |

When using HTTP RPC, provide the eight-character key index followed by the key itself (standard Odoo API key format).
The admin API key intentionally starts with `admin-` to ensure a unique key index.

## Operational Notes

- Provisioning is skipped if `ODOO_KEY` is blank or unset.
- To rotate credentials, update `ODOO_KEY` and rerun `uv run restore <stack>`. The script regenerates both passwords
  and API keys.
- Remove access by clearing `ODOO_KEY` and running the restore task again or deleting the users/keys in Odoo Settings.

## Related Commands

- `uv run restore <stack>`
