# AGENTS.md — notification_center

## Scope

- Channel notifications + alert history model.
- Keep logic generic (no client-specific routing).

## Notes

- Uses `notification.history` model for rate limiting.
- Depends on `transaction_utilities` for safe cursor handling.
