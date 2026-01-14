---
title: Authentik SSO
---

Purpose

- Capture how Authentik is wired to Odoo and the expected launch/login behavior.

## Provider setup

- Use an OAuth2/OpenID Provider with a public client.
- Authorization flow: `default-provider-authorization-implicit-consent`.
- Redirect URI: `https://<odoo-host>/auth_oauth/signin`.
- Response types must include `id_token token` (Odoo consumes the access token).

## Odoo integration

- The `authentik_sso` addon overrides the Authentik auth link to request `id_token token`.
- Launch URL for Authentik apps: `https://<odoo-host>/authentik/login`.
- Required env: `ENV_OVERRIDE_AUTHENTIK__CLIENT_ID` and `ENV_OVERRIDE_AUTHENTIK__BASE_URL`.
- Auto-provisioning requires `auth_signup.invitation_scope = b2c`.

## Group mapping

- `ENV_OVERRIDE_AUTHENTIK__GROUP_CLAIM` provides the claim with group names.
- `ENV_OVERRIDE_AUTHENTIK__ADMIN_GROUP` names the admin group (default: `authentik Admins`).
