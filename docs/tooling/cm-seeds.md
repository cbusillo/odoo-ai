---
title: CM Seed Data (Git-Ignored)
---

Purpose

- Keep company-specific seed data out of git while still loading structured
  defaults into Odoo.

How it works

- The CM seed loader reads a JSON file from a git-ignored path.
- If the seed file is not configured, it falls back to config parameters.
- Seed records are created or updated idempotently.

Configuration

- Preferred: set a seed file path in env or config.
- Config param: `cm_seed.file_path`
- Env vars (fallbacks):
  - `CM_SEED_FILE_PATH`
  - `ENV_OVERRIDE_CONFIG_PARAM__CM_SEED__FILE_PATH`

Data sources

- RepairShopr ticket settings (return methods, delivery days, location
  dropdowns) are now sourced from the **RepairShopr sync DB** tables:
  - `repairshopr_data_ticket_types`
  - `repairshopr_data_ticket_type_fields`
  - `repairshopr_data_ticket_type_field_answers`

Recommended file location

- `tmp/seeds/cm_seed.json` (ignored by git because `/tmp/*` is ignored).

Seed file schema

The seed file must be a JSON object with these keys. Each key holds an array
of objects.

- `billing_requirements`
- `billing_contexts`
- `helpdesk_stages`
- `helpdesk_tags`
- `qc_checklist`
- `return_methods`
- `diagnostic_tests`
- `location_options`
- `location_option_aliases`
- `delivery_days`
- `delivery_day_aliases`
- `return_methods`
- `return_method_aliases`

Example (template only, no real data)

```json
{
  "billing_requirements": [
    {
      "name": "Claim Number",
      "code": "claim_number",
      "sequence": 10,
      "is_required": true,
      "requirement_group": "both",
      "target_model": "service.invoice.order",
      "field_name": "claim_number"
    }
  ],
  "billing_contexts": [
    {
      "name": "Warranty Vendor",
      "code": "warranty_vendor",
      "sequence": 10,
      "requirements": ["claim_number", "location", "delivery_day"],
      "requires_estimate": false,
      "requires_claim_approval": true
    }
  ],
  "helpdesk_stages": [
    {
      "name": "Intake - New",
      "sequence": 10,
      "is_close": false,
      "fold": false
    }
  ],
  "helpdesk_tags": [
    {"name": "Queue - Example"}
  ],
  "qc_checklist": [
    {
      "name": "Verify serial number matches paperwork",
      "category": "paperwork",
      "sequence": 10
    }
  ],
  "return_methods": [
    {
      "name": "Deliver By CM",
      "external_key": "131790"
    }
  ],
  "return_method_aliases": [
    {"name": "Deliver By CM", "external_key": "131790"},
    {"name": "Pickup By BOCES", "external_key": "131789"}
  ],
  "location_options": [
    {
      "name": "RVC Admin Building",
      "location_type": "location"
    },
    {
      "name": "Holy Cross HS",
      "location_type": "dropoff"
    }
  ],
  "location_option_aliases": [
    {
      "name": "RVC Admin Building",
      "location_type": "location",
      "external_key": "154898"
    }
  ],
  "delivery_days": [
    {"name": "Monday"}
  ],
  "delivery_day_aliases": [
    {"name": "Monday", "external_key": "153438"}
  ],
  "diagnostic_tests": [
    {"name": "Serial number matches paperwork"}
  ]
}
```

Operational notes

- The seed loader runs during `post_init_hook` for `cm_data_import`.
- You can rerun it from the CM configuration menu:
  `CM Configuration -> Run CM Seed Loader` (admin only).

Keep this doc up to date

- If you add or change seed loader keys, update this doc.
- If you add new structured models that require seed data, add them here.
