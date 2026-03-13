---
title: CM Import Baseline
---


Purpose

- Freeze the current `cm-local` import baseline from live evidence before
  importer redesign or cleanup work.

When captured

- Snapshot probe executed on March 13, 2026 against local database `cm`.
- Runtime command path was proven with:
  - `uv run platform up --context cm --instance local`
  - `uv run platform odoo-shell --context cm --instance local --script tmp/scripts/cm_import_baseline_probe.py`

Evidence sources

- Live snapshot file: `tmp/cm_import_baseline_probe.json`
- RepairShopr scheduled-run log: `tmp/repairshopr-scheduled-import-20260313-130928.log`
- Importer entrypoints:
  - `addons/cm_data_import/models/cm_data_importer.py`
  - `addons/repairshopr_import/models/repairshopr_importer.py`
  - `addons/fishbowl_import/models/fishbowl_importer.py`

Completion contract proven from code

- All three importers expose `run_scheduled_import()` and `run_full_import()`.
- Scheduled runs use `transaction.cron_budget.mixin` and record terminal state in
  `ir.config_parameter` as `success`, `partial`, or `failed`.
- Success/partial/failure keys:
  - CM data: `cm_data.last_run_*`, `cm_data.last_sync_at`
  - RepairShopr: `repairshopr.last_run_*`, `repairshopr.last_sync_at`
  - Fishbowl: `fishbowl.last_run_*`, `fishbowl.last_sync_at`

## CM Data Baseline

Current status

- `last_run_status=success`
- `last_run_at=2026-03-12 23:31:55`
- `last_sync_at=2026-03-12 23:30:11`

Source counts vs imported counts

- Accounts: source `171`, imported external IDs `171`.
- Contacts: source `234`, imported external IDs `225`.
- Directions: source `214`, imported external IDs `214`.
- Shipping instructions: source `28`, imported external IDs `28`.
- Delivery logs: source `6960`, imported external IDs `6960`.
- Price lists: source `3`, imported external IDs `3`.
- Pricing catalogs: source `5`, imported external IDs `3`.
- Pricing lines: source `4028`, imported external IDs `2501`.
- Employees: source `57`, imported external IDs `57`; current `hr.employee`
  row count is `43` because the model contains merged operational employees,
  not one isolated row per source record.
- PTO usage: source `10931`, imported external IDs `10931`.
- Vacation usage: source `145`, imported external IDs `145`.
- Timeclock punches: source `34126`, imported external IDs `3976` in + `3973`
  out. Current `hr.attendance` row count is `3981`, so attendance is clearly
  not a raw punch mirror.

Legitimate differences proven from code

- Contacts are skipped when `account_name` cannot be matched to an imported CM
  account partner.
- Passwords are skipped when `account_name` has no matching partner, and they
  also dedupe by `(partner_id, sub_name, user_name)` instead of storing one row
  per source record.
- Pricing catalog rows with `code == "regular"` are intentionally not imported
  to `school.pricing.catalog`.
- Regular pricing lines are intentionally audited against product list prices
  and are not imported to `school.pricing.matrix`.
- Pricing rows for unresolved partner-linked catalogs are audited and skipped.

Pricing audit snapshot

- `missing_catalog=2470`
- `missing_partner=7`
- `missing_product=7585`

Operational CM backbone gaps visible now

- `account.routing.rule=0`
- `shipping.profile=0`
- `school.delivery.day.alias=0`

Interpretation

- `cm_data_import` is the only importer with a currently proven successful run
  on this local database.
- CM backbone/rule objects are still incomplete even though the main CM staging
  and operational counts are substantial.

## RepairShopr Baseline

Current status

- No recorded `repairshopr.last_run_status` or `repairshopr.last_sync_at` was
  present before reproduction.
- Current local data contains RepairShopr-linked records, but they are not tied
  to a recent recorded terminal run.

Importer-scope source counts

- Customers: `142`
- Contacts: `264`
- Products: `2240`
- Tickets in scope (created/updated on or after January 1, 2022): `133632`
- Ticket properties in scope: `133632`
- Ticket comments in scope: `1276110`
- Estimates in scope: `15817`
- Estimate line items in scope: `88692`
- Invoices in scope: `131138`
- Invoice line items in scope: `444114`

Current imported counts

- Customer external IDs: `150`
- Contact external IDs: `263`
- Product external IDs: `931`
- Ticket external IDs: `118250`
- `account.move=0`
- `service.intake.order=0`
- `service.transport.order.device=0`

Legitimate differences proven from code

- Transaction-bearing imports use a hard cutoff of January 1, 2022.
- Placeholder partners can be created from downstream records even when a
  customer row was not imported first, so customer external IDs can exceed the
  raw customer table count.

Reproduction signal from live scheduled run

- Scheduled run started with an effective runtime budget of `1785s`.
- The run cleared products first, then entered the ticket phase.
- By `2026-03-13 17:10:26`, the scheduled run had only reached `6100` ticket
  commits out of `133632` in-scope tickets.

Interpretation

- The current scheduled path appears likely to spend most or all of its budget
  in ticket ingestion before estimates or invoices can complete.
- That matches the observed absence of invoice-layer target records better than
  the old assumption that invoices are the first failing phase.

## Fishbowl Baseline

Current status

- No recorded `fishbowl.last_run_status` or `fishbowl.last_sync_at` was present
  before reproduction.

Source counts

- Customers: `88`
- Vendors: `33`
- Addresses: `136`
- UoM: `18`
- Parts: `3466`
- Products: `3423`
- Sales orders: `10594`
- Sales order lines: `189002`
- Purchase orders: `6952`
- Purchase order lines: `15522`
- Shipped shipments: `11348`
- Shipped shipment lines: `186976`
- Done receipts: `6457`
- Done receipt lines: `14709`

Current imported counts

- Customer external IDs: `88`
- Vendor external IDs: `33`
- Address external IDs: `134`
- UoM external IDs: `18`
- Product external IDs: `3377`
- Part external IDs: `3462`
- Sales orders external IDs: `10587`
- Sales order lines external IDs: `188840`
- Purchase orders external IDs: `6947`
- Purchase order lines external IDs: `15509`
- Shipments external IDs: `11341`
- Shipment lines external IDs: `59500`

Legitimate differences proven from code

- Shipments only import rows with `dateShipped IS NOT NULL` and ship status
  `shipped`.
- Receipts only import rows with `dateReceived IS NOT NULL` and status
  `received` or `fulfilled`.

Interpretation

- Order-layer coverage is close to source counts.
- Shipment header coverage is close, but shipment-line coverage is far behind,
  which keeps the shipment timeout suspicion alive.

## Immediate Next Questions

- Let the current scheduled RepairShopr reproduction finish and record whether
  it ends as `partial`, `failed`, or `success`.
- Re-run the live probe immediately after that run to freeze the post-run delta.
- Reproduce Fishbowl through the scheduled path after RepairShopr completes so
  the same terminal-state evidence exists there.
