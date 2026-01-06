---
title: Odoo 19 Upgrade (OPW)
---


## Constraints

- Cannot use Odoo Upgrade platform (no database upload).
- Must upgrade Odoo 18 Enterprise database to Odoo 19 and preserve full history
  and relations.
- Timeline is flexible.

## product_connect dependencies

From `addons/product_connect/__manifest__.py` (version 19.0.8.2):

- base
- product
- web
- web_tour
- website_sale
- base_automation
- stock
- mail
- project
- repair
- contacts
- account
- sale_management
- purchase
- phone_validation
- delivery
- delivery_ups_rest
- delivery_usps_rest
- base_geolocalize
- external_ids
- hr_employee_name_extended
- discuss_record_links
- disable_odoo_online

## Dependency classification (product_connect)

| Dependency | Repo location | Opw DB state (2026-01-05) | License (DB) |
| --- | --- | --- | --- |
| account | core (Odoo) | installed | LGPL-3 |
| base | core (Odoo) | installed | LGPL-3 |
| base_automation | core (Odoo) | installed | LGPL-3 |
| base_geolocalize | core (Odoo) | installed | LGPL-3 |
| contacts | core (Odoo) | installed | LGPL-3 |
| delivery | core (Odoo) | installed | LGPL-3 |
| delivery_ups_rest | enterprise | installed | OEEL-1 |
| delivery_usps_rest | enterprise | installed | OEEL-1 |
| disable_odoo_online | core (Odoo) | installed | LGPL-3 |
| discuss_record_links | custom (addons) | missing from DB | |
| external_ids | custom (addons) | missing from DB | |
| hr_employee_name_extended | custom (addons) | missing from DB | |
| mail | core (Odoo) | installed | LGPL-3 |
| phone_validation | core (Odoo) | installed | LGPL-3 |
| product | core (Odoo) | installed | LGPL-3 |
| project | core (Odoo) | installed | LGPL-3 |
| purchase | core (Odoo) | installed | LGPL-3 |
| repair | core (Odoo) | installed | LGPL-3 |
| sale_management | core (Odoo) | installed | LGPL-3 |
| stock | core (Odoo) | installed | LGPL-3 |
| web | core (Odoo) | installed | LGPL-3 |
| web_tour | core (Odoo) | installed | LGPL-3 |
| website_sale | core (Odoo) | installed | LGPL-3 |

Notes:

- discuss_record_links, external_ids, and hr_employee_name_extended are
  present in the repo but do not exist in the current opw database module table.
  This likely
  reflects the Odoo 19 manifest vs the Odoo 18 database state and will need
  review during migration.
- Custom dependency paths: addons/discuss_record_links, addons/external_ids,
  addons/hr_employee_name_extended.
- The Odoo 19 container cannot open the Odoo 18 schema in opw-local (missing
  res_partner.suggest_based_on). Use SQL queries for inventory until migration.

## Application modules (opw-local snapshot 2026-01-05)

- account (LGPL-3)
- calendar (LGPL-3)
- contacts (LGPL-3)
- crm (LGPL-3)
- delivery_ups_rest (OEEL-1, enterprise)
- delivery_usps_rest (OEEL-1, enterprise)
- hr (LGPL-3)
- hr_recruitment (LGPL-3)
- hr_skills (LGPL-3)
- im_livechat (LGPL-3)
- knowledge (OEEL-1, enterprise)
- mail (LGPL-3)
- product_connect (LGPL-3, custom)
- project (LGPL-3)
- project_todo (LGPL-3)
- purchase (LGPL-3)
- repair (LGPL-3)
- sale_management (LGPL-3)
- stock (LGPL-3)
- web_studio (OEEL-1, enterprise)
- website (LGPL-3)
- website_event (LGPL-3)
- website_hr_recruitment (LGPL-3)
- website_sale (LGPL-3)
- website_slides (LGPL-3)

## Application module dependencies (opw-local snapshot 2026-01-05)

- account: analytic, base_setup, digest, onboarding, portal, product
- calendar: base, mail
- contacts: base, mail
- crm: base_setup, calendar, contacts, digest, mail, phone_validation,
  resource, sales_team, utm, web_tour
- delivery_ups_rest: mail, stock_delivery
- delivery_usps_rest: mail, stock_delivery
- hr: base_setup, digest, phone_validation, resource_mail, web
- hr_recruitment: attachment_indexation, calendar, digest, hr, utm, web_tour
- hr_skills: hr
- im_livechat: digest, mail, rating, utm
- knowledge: digest, html_editor, mail, portal, web, web_editor, web_hierarchy,
  web_unsplash
- mail: base, base_setup, bus, html_editor, web_tour
- product_connect: account, base, base_automation, base_geolocalize, contacts,
  delivery, delivery_ups_rest, delivery_usps_rest, mail, phone_validation,
  product, project, purchase, repair, sale_management, stock, web,
  website_sale, web_tour
- project: analytic, base_setup, digest, mail, portal, rating, resource, web,
  web_tour
- project_todo: project
- purchase: account
- repair: sale_management, stock
- sale_management: digest, sale
- stock: barcodes_gs1_nomenclature, digest, product
- web_studio: base_automation, base_import_module, html_editor, mail, sms, web,
  web_cohort, web_editor, web_enterprise, web_gantt, web_map
- website: auth_signup, digest, google_recaptcha, http_routing, mail, portal,
  social_media, utm, web, web_editor
- website_event: event, website, website_mail, website_partner
- website_hr_recruitment: hr_recruitment, website_mail
- website_sale: delivery, digest, portal_rating, sale, website, website_mail,
  website_payment
- website_slides: portal_rating, website, website_mail, website_profile

## Enterprise dependencies of application modules (direct)

Snapshot: 2026-01-05.

- product_connect: delivery_ups_rest (OEEL-1), delivery_usps_rest (OEEL-1)
- web_studio: web_cohort, web_enterprise, web_gantt, web_map (OEEL-1)

## OpenUpgrade provisioning (repeatable)

- OpenUpgrade is sourced via ODOO_ADDON_REPOSITORIES at image build time using
  docker/scripts/fetch_addons.sh.
- The clone step requires GITHUB_TOKEN, even for public repositories.
- opw-local sets a full ODOO_ADDON_REPOSITORIES list (no variable expansion in
  env files) and includes OCA/OpenUpgrade@19.0 via
  docker/config/opw-local.env.
- opw-local enables OPENUPGRADE_ENABLED=1 and pins OPENUPGRADE_TARGET_VERSION=19.0.
- OpenUpgrade installs openupgradelib during image build when
  /opt/extra_addons/openupgrade_framework is present (pinned to 3.12.0).
- OpenUpgrade scripts are resolved from either /opt/extra_addons/openupgrade_scripts
  or /opt/extra_addons/OpenUpgrade/openupgrade_scripts.
- OpenUpgrade 19.0 repo currently lacks a scripts/ directory, so the restore
  step fails early with "OpenUpgrade scripts not found" until scripts are added.
- Custom scripts now live at /volumes/addons/openupgrade_scripts_custom/scripts
  (wired via OPENUPGRADE_SCRIPTS_PATH).

## Restore pipeline (upgrade)

- OPENUPGRADE_ENABLED triggers OpenUpgrade during restore, so
  uv run ops local restore opw restores + upgrades in one step.
- OpenUpgrade runs after the upstream restore and before sanitize/update_addons.
- OPENUPGRADE_SKIP_UPDATE_ADDONS defaults to 1 to avoid double-updating modules
  after OpenUpgrade runs with --update all.
- Use uv run ops local openupgrade opw to re-run OpenUpgrade without restoring.

## OpenUpgrade run notes (2026-01-05)

- OpenUpgrade failed in stock module while loading
  stock/views/stock_rule_views.xml: missing external ID
  stock.ir_cron_scheduler_action_ir_actions_server.
- Added custom OpenUpgrade script to recreate the missing server action and
  external ID before stock loads:
  addons/openupgrade_scripts_custom/scripts/stock/19.0.1.1/pre-migration.py.
- `uv run ops local openupgrade opw` now resets `ir_module_module.latest_version`
  to `0.0.0` for modules that have OpenUpgrade scripts so re-runs execute
  migration hooks after partial failures.
- product_connect 18.x pre-migrations now fall back to OpenUpgrade helpers when
  `odoo.upgrade.util` is unavailable (Odoo 19).
- OpenUpgrade completed successfully via `uv run ops local openupgrade opw`.
  Warnings captured:
  - modules not installable: account_auto_transfer, account_disallowed_expenses,
    sale_async_emails, web_editor.
  - unique index `mail_link_preview_unique_source_url` could not be created due
    to duplicate `mail_link_preview.source_url` rows (Odoo 18 stored one row per
    message, Odoo 19 expects one row per URL).
  - web_editor models declared but not loadable (likely because web_editor is
    missing).
- Added custom OpenUpgrade hooks that mark missing-manifest modules (including
  `web_editor`) uninstalled and remove `web_editor.*` model metadata to prevent
  registry warnings.
- As of 2026-01-06, added a custom OpenUpgrade hook in
  `addons/openupgrade_scripts_custom/scripts/mail/` that de-duplicates
  `mail_link_preview` and ensures the `mail_link_preview_unique_source_url`
  index can be created.
- Cleanup ran after the latest OpenUpgrade run; `web_editor` is now
  `uninstalled` and `web_editor.*` models were removed from `ir_model`.

## Installed modules (opw-local snapshot 2026-01-05)

- Total installed modules: 178
- License breakdown: LGPL-3 (146), OEEL-1 (31), OPL-1 (1)

Enterprise / proprietary modules (OEEL-1 or OPL-1):

- contacts_enterprise
- crm_enterprise
- delivery_ups_rest
- delivery_usps_rest
- digest_enterprise
- event_enterprise
- hr_gantt
- hr_mobile
- knowledge
- l10n_us_check_printing
- mail_enterprise
- mail_mobile
- product_barcodelookup
- project_enterprise
- project_enterprise_hr
- project_enterprise_hr_skills
- project_hr_skills
- spreadsheet_dashboard_crm
- spreadsheet_dashboard_edition
- spreadsheet_edition
- spreadsheet_sale_management
- studio_customization
- web_cohort
- web_enterprise
- web_gantt
- web_map
- web_mobile
- web_studio
- website_enterprise
- website_knowledge
- website_product_barcodelookup
- website_studio

All installed modules (alphabetical):

- account
- account_check_printing
- account_edi_ubl_cii
- account_payment
- analytic
- attachment_indexation
- auth_signup
- auth_totp
- auth_totp_mail
- auth_totp_portal
- barcodes
- barcodes_gs1_nomenclature
- base
- base_automation
- base_geolocalize
- base_import
- base_import_module
- base_install_request
- base_setup
- bus
- calendar
- calendar_sms
- contacts
- contacts_enterprise
- crm
- crm_enterprise
- crm_livechat
- crm_sms
- delivery
- delivery_ups_rest
- delivery_usps_rest
- digest
- digest_enterprise
- disable_odoo_online
- event
- event_crm
- event_crm_sale
- event_enterprise
- event_product
- event_sale
- event_sms
- gamification
- gamification_sale_crm
- google_recaptcha
- hr
- hr_calendar
- hr_gamification
- hr_gantt
- hr_hourly_cost
- hr_livechat
- hr_mobile
- hr_org_chart
- hr_recruitment
- hr_recruitment_skills
- hr_skills
- hr_skills_slides
- html_editor
- http_routing
- iap
- iap_crm
- iap_mail
- im_livechat
- knowledge
- l10n_us
- l10n_us_account
- l10n_us_check_printing
- mail
- mail_bot
- mail_bot_hr
- mail_enterprise
- mail_mobile
- onboarding
- partner_autocomplete
- payment
- phone_validation
- portal
- portal_rating
- privacy_lookup
- product
- product_barcodelookup
- product_connect
- project
- project_account
- project_enterprise
- project_enterprise_hr
- project_enterprise_hr_skills
- project_hr_skills
- project_purchase
- project_purchase_stock
- project_sms
- project_stock
- project_stock_account
- project_todo
- purchase
- purchase_edi_ubl_bis3
- purchase_repair
- purchase_stock
- rating
- repair
- resource
- resource_mail
- sale
- sale_crm
- sale_edi_ubl
- sale_management
- sale_pdf_quote_builder
- sale_project
- sale_project_stock
- sale_project_stock_account
- sale_purchase
- sale_purchase_project
- sale_purchase_stock
- sale_service
- sale_sms
- sale_stock
- sales_team
- sms
- snailmail
- snailmail_account
- social_media
- spreadsheet
- spreadsheet_account
- spreadsheet_dashboard
- spreadsheet_dashboard_account
- spreadsheet_dashboard_crm
- spreadsheet_dashboard_edition
- spreadsheet_dashboard_event_sale
- spreadsheet_dashboard_im_livechat
- spreadsheet_dashboard_sale
- spreadsheet_dashboard_stock_account
- spreadsheet_dashboard_website_sale
- spreadsheet_edition
- spreadsheet_sale_management
- stock
- stock_account
- stock_delivery
- stock_sms
- studio_customization
- theme_default
- uom
- utm
- web
- web_cohort
- web_editor
- web_enterprise
- web_gantt
- web_hierarchy
- web_map
- web_mobile
- web_studio
- web_tour
- web_unsplash
- website
- website_blog
- website_crm
- website_crm_livechat
- website_crm_sms
- website_enterprise
- website_event
- website_event_crm
- website_event_sale
- website_forum
- website_google_map
- website_hr_recruitment
- website_knowledge
- website_livechat
- website_mail
- website_partner
- website_payment
- website_product_barcodelookup
- website_profile
- website_project
- website_sale
- website_sale_stock
- website_slides
- website_slides_forum
- website_sms
- website_studio

## Plan (primary: keep Enterprise)

- Keep Enterprise modules installed and migrate in-place using OpenUpgrade
  19.0 plus custom migration scripts.
- Implement custom migration steps for any Enterprise modules that are not
  covered by OpenUpgrade scripts.
- Validate full history and relational integrity after each migration run.

## Plan (fallback: remove Enterprise)

- If Enterprise migrations block progress, remove non-essential Enterprise
  modules in Odoo 18 first.
- Re-run the migration on the reduced module set.
- Document any data loss or behavior changes from removing Enterprise.

## Progress log

- 2026-01-05: Created this tracker and captured `product_connect` dependencies.
- 2026-01-05: Added dependency classification and opw-local module inventory
  (SQL snapshot).
- 2026-01-05: Added application modules and dependency map (SQL snapshot).
- 2026-01-05: Documented OpenUpgrade provisioning and appended repo for opw-local.
- 2026-01-05: Added restore pipeline draft for OpenUpgrade integration.
- 2026-01-05: Wired OpenUpgrade env toggles and restore hook (local restore).
- 2026-01-05: Restore failed because OpenUpgrade 19.0 lacks scripts/ directory.
- 2026-01-05: Added custom OpenUpgrade scripts path and stubs for custom modules.
- 2026-01-05: opw-local restore + OpenUpgrade completed; module state warnings
  for account_auto_transfer, account_disallowed_expenses, sale_async_emails,
  web_editor.
- 2026-01-05: Added run_openupgrade runner and ops local openupgrade command.
- 2026-01-05: Added OpenUpgrade script stubs for custom modules at 19.0 versions.
