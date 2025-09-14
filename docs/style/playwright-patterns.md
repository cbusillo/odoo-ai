# Playwright Patterns

Principles

- Prefer role/name selectors; avoid brittle CSS chains.
- Make steps idempotent; add explicit waits for state not time.
- Keep tours short; move logic to unit/JS tests.

Patterns

- Navigation: wait for key UI markers (breadcrumbs, app menu) before interaction.
- Forms: wait for form mount, then interact; verify via field values not sleeps.
- Lists: use role=row and text filters; avoid nth-child.
- Dialogs: wait for dialog role, then target buttons by name.

Debugging

- Capture screenshot and accessibility snapshot at failure.
- Collect browser console messages; search for uncaught errors.
- Reduce flakiness by replacing sleeps with waits on UI conditions.
