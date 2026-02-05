import logging
import threading
import traceback
from contextlib import contextmanager
from time import sleep
from typing import Generator, Union

from babel.dates import format_timedelta
from httpx import RequestError
from odoo import api, fields, models
from odoo.tools import config
from psycopg2 import InterfaceError, OperationalError
from psycopg2.errors import InFailedSqlTransaction, SerializationFailure, TransactionRollbackError
from pydantic import BaseModel

from ..services.shopify.helpers import (
    DEFAULT_DATETIME,
    OdooDataError,
    ShopifyApiError,
    ShopifyStaleRunTimeout,
    ShopifySyncRunFailed,
    SyncMode,
    format_datetime_for_shopify,
    last_import_config_key,
)

_logger = logging.getLogger(__name__)


class ShopifySync(models.TransientModel):
    _name = "shopify.sync"
    _description = "Shopify Sync"
    _inherit = ["mail.activity.mixin", "mail.thread", "notification.manager.mixin", "transaction.mixin"]
    _transient_max_hours = 24 * 7
    _transient_max_count = 1000

    MAX_RETRY_ATTEMPTS = 20
    RETRYABLE_ERRORS = (
        ShopifyApiError,
        OdooDataError,
        TransactionRollbackError,
        SerializationFailure,
        OperationalError,
        InterfaceError,
        RequestError,
    )

    LOCK_ID = 87945012
    IMPORT_EXPORT_CRON_TIME = 60 * 60
    CRON_IDLE_TIMEOUT_THRESHOLD_SECONDS = 10 * 60

    create_time_human = fields.Char(compute="_compute_create_time_human", string="Created")
    start_time = fields.Datetime()
    start_time_human = fields.Char(compute="_compute_start_time_human", string="Started")
    end_time = fields.Datetime()
    end_time_human = fields.Char(compute="_compute_end_time_human", string="Ended")
    run_time = fields.Float(compute="_compute_run_time", string="Run Time (seconds)")
    run_time_human = fields.Char(compute="_compute_run_time", string="Run Time")

    mode = fields.Selection(SyncMode.choices(), required=True, index=True)
    odoo_products_to_sync = fields.Many2many("product.product")
    shopify_product_id_to_sync = fields.Char(string="Shopify Product ID")
    datetime_to_sync = fields.Datetime()
    updated_count = fields.Integer()
    total_count = fields.Integer()
    progress_percent = fields.Float(string="Progress %", compute="_compute_progress_percent", store=True)
    hard_throttle_count = fields.Integer(default=0)
    retry_attempts = fields.Integer(default=0)

    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("queued", "Queued"),
            ("running", "Running"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        default="draft",
        required=True,
        index=True,
    )

    user = fields.Many2one("res.users", default=lambda self: self.env.user)
    last_import_start_time = fields.Datetime()

    error_message = fields.Text()
    error_traceback = fields.Text()
    error_exception = fields.Text()
    error_odoo_record = fields.Many2one("product.product")
    error_shopify_record = fields.Json()
    error_shopify_input = fields.Json()

    @api.model
    def fields_get(self, allfields: list[str] | None = None, attributes: list[str] | None = None) -> dict[str, dict]:
        resource = super().fields_get(allfields, attributes)
        if (
            (mode := resource.get("mode"))
            and (selection := mode.get("selection"))
            and not self.env["ir.config_parameter"].sudo().get_param("shopify.test_store")
        ):
            mode["selection"] = [select for select in selection if select[0] != "reset_shopify"]

        return resource

    @staticmethod
    def _is_duplicate(vals: "odoo.values.shopify_sync", duplicates: "odoo.model.shopify_sync") -> bool:
        if vals["mode"] == SyncMode.EXPORT_BATCH_PRODUCTS:
            command = vals.get("odoo_products_to_sync") or []
            ids = tuple(sorted(command[0][2])) if command and command[0][0] == 6 else ()
            duplicates = duplicates.filtered(lambda sync, s_ids=ids: tuple(sorted(sync.odoo_products_to_sync.ids)) == s_ids)
        return bool(duplicates)

    @api.model_create_multi
    def create(self, vals_list: Union["odoo.values.shopify_sync", list["odoo.values.shopify_sync"]]) -> "odoo.model.shopify_sync":
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        vals_to_create: list["odoo.values.shopify_sync"] = []
        with self._advisory_lock(self.LOCK_ID) as lock_acquired:
            if lock_acquired:
                self._fail_stale_runs()

            for vals in vals_list:
                existing = [
                    ("mode", "=", vals["mode"]),
                    ("state", "=", "queued"),
                    ("shopify_product_id_to_sync", "=", vals.get("shopify_product_id_to_sync")),
                    ("datetime_to_sync", "=", vals.get("datetime_to_sync")),
                ]
                potential = self.search(existing)
                if self._is_duplicate(vals, potential):
                    _logger.debug(f"Duplicate Shopify sync found: {vals['mode']}")
                    continue

                vals_to_create.append(vals)
        self._safe_commit()

        if not vals_to_create:
            return self.browse()

        syncs = super().create(vals_to_create)
        syncs.state = "queued"
        self._safe_commit()
        return syncs

    def unlink(self) -> "odoo.model.shopify_sync":
        self.env["mail.activity"].search([("res_id", "in", self.ids)]).unlink()
        self.env["mail.message"].search([("res_id", "in", self.ids)]).unlink()

        return super().unlink()

    @api.depends("updated_count", "total_count")
    def _compute_progress_percent(self) -> None:
        for record in self:
            record.progress_percent = (record.updated_count / record.total_count) * 100 if record.total_count else 0.0

    def _compute_create_time_human(self) -> None:
        for record in self:
            if record.create_date:
                record.create_time_human = format_timedelta(fields.Datetime.now() - record.create_date, locale="en_US")
                record.create_time_human += " ago"
            else:
                record.create_time_human = "-"

    def _compute_start_time_human(self) -> None:
        for record in self:
            if record.start_time:
                record.start_time_human = format_timedelta(fields.Datetime.now() - record.start_time, locale="en_US")
                record.start_time_human += " ago"
            else:
                record.start_time_human = "-"

    def _compute_end_time_human(self) -> None:
        for record in self:
            if record.end_time:
                record.end_time_human = format_timedelta(fields.Datetime.now() - record.end_time, locale="en_US")
                record.end_time_human += " ago"
            else:
                record.end_time_human = "-"

    def _compute_run_time(self) -> None:
        for record in self:
            if record.end_time and record.start_time:
                time_delta = record.end_time - record.start_time
                record.run_time = time_delta.total_seconds()
                record.run_time_human = format_timedelta(time_delta, locale="en_US")
            else:
                record.run_time = 0.0
                record.run_time_human = "-"

    def _fail_stale_runs(self, threshold_seconds: int = 0) -> None:
        if not threshold_seconds:
            threshold_seconds = self.CRON_IDLE_TIMEOUT_THRESHOLD_SECONDS

        cutoff = fields.Datetime.subtract(fields.Datetime.now(), seconds=threshold_seconds)
        cr = self.env.cr
        cr.execute("SELECT id FROM shopify_sync WHERE state = 'running' AND write_date < %s FOR UPDATE SKIP LOCKED", [cutoff])
        stale_ids = [row[0] for row in cr.fetchall()]
        if not stale_ids:
            return

        stale_runs = self.browse(stale_ids)

        for run in stale_runs:
            if run.retry_attempts < run.MAX_RETRY_ATTEMPTS:
                stale_message = f"Stale sync {run.id} (run {run.retry_attempts + 1}/{run.MAX_RETRY_ATTEMPTS})"
                run.write(
                    {
                        "state": "queued",
                        "retry_attempts": run.retry_attempts + 1,
                        "error_message": run.error_message + "\n" + stale_message if run.error_message else stale_message,
                        "start_time": False,
                        "end_time": False,
                    }
                )
                _logger.warning(f"Re-queued stale sync {run.id} (run {run.retry_attempts + 1}/{run.MAX_RETRY_ATTEMPTS})")
            else:
                vals = run._prepare_failure_vals(ShopifyStaleRunTimeout(f"No activity for {threshold_seconds}s"))
                vals["end_time"] = run.write_date
                run.write(vals)

    @api.model
    def _cron_dispatch_next(self) -> None:
        while True:
            with self._advisory_lock(self.LOCK_ID) as lock_acquired:
                if not lock_acquired:
                    _logger.debug("Another worker already running; skipping.")
                    return

                self._fail_stale_runs()
                if self.search([("state", "=", "running")], limit=1):
                    _logger.debug("Sync already running; skipping.")
                    return

                next_sync = self.search(
                    [("state", "=", "queued")],
                    order="retry_attempts desc, id asc",
                    limit=1,
                )
                if next_sync:
                    next_sync.write(
                        {
                            "state": "running",
                            "start_time": fields.Datetime.now(),
                        }
                    )
            self._safe_commit()

            if not next_sync:
                _logger.debug("No queued syncs found; exiting dispatcher.")
                break

            try:
                next_sync._execute_mode()
            except (ShopifyApiError, OdooDataError, ShopifySyncRunFailed):
                self._safe_rollback()
                try:
                    self._safe_commit()
                except (SerializationFailure, InFailedSqlTransaction, TransactionRollbackError):
                    _logger.debug("Commit after rollback failed, continuing")
                continue
            except Exception:
                self._safe_rollback()
                raise

        if self.search([("state", "in", ["running", "queued"])], limit=1):
            _logger.debug("Another sync is running; exiting dispatcher.")
            return

        now = fields.Datetime.now()
        cutoff = fields.Datetime.subtract(now, seconds=self.IMPORT_EXPORT_CRON_TIME)

        def _is_healthy(mode: SyncMode) -> bool:
            in_flight = self.search_count([("mode", "=", mode.value), ("state", "in", ["queued", "running"])])
            recent = self.search_count([("mode", "=", mode.value), ("state", "=", "success"), ("start_time", ">=", cutoff)])
            return bool(in_flight or recent)

        healthy_import = _is_healthy(SyncMode.IMPORT_THEN_EXPORT_PRODUCTS)
        healthy_export = _is_healthy(SyncMode.EXPORT_CHANGED_PRODUCTS)

        if not (healthy_import and healthy_export):
            self.create({"mode": SyncMode.IMPORT_THEN_EXPORT_PRODUCTS.value})

    def run_async(self) -> None:
        if config["stop_after_init"]:
            _logger.debug("Skipping async sync in stop_after_init mode")
            return

        if self.env.context.get("skip_shopify_sync"):
            _logger.debug("Skipping async sync due to skip_shopify_sync context")
            return

        _logger.debug(f"Running async sync for {self}")

        def run_in_thread() -> None:
            with self.env.registry.cursor() as cr:
                thread_env = self.env(cr)
                sync_jobs = thread_env["shopify.sync"].sudo().browse(self.ids)
                for sync_job in sync_jobs:
                    sync_job._cron_dispatch_next()

        threading.Thread(target=run_in_thread, daemon=True).start()

    def create_and_run_async(
        self, vals_list: Union["odoo.values.shopify_sync", list["odoo.values.shopify_sync"]]
    ) -> "odoo.model.shopify_sync":
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        sync_jobs = self.create(vals_list)
        if sync_jobs:
            sync_jobs.run_async()
        return sync_jobs

    def duplicate_and_run_async(self) -> "odoo.model.shopify_sync":
        new_syncs = self.duplicate()
        new_syncs.run_async()
        return new_syncs

    def duplicate(self) -> "odoo.model.shopify_sync":
        new_syncs = self.env["shopify.sync"]
        for sync in self:
            new_sync = sync.create(
                {
                    "mode": sync.mode,
                    "datetime_to_sync": sync.datetime_to_sync,
                    "odoo_products_to_sync": sync.odoo_products_to_sync,
                    "shopify_product_id_to_sync": sync.shopify_product_id_to_sync,
                }
            )
            new_syncs |= new_sync
        return new_syncs

    @api.model
    def _execute_mode(self) -> None:
        if self.mode not in {m.value for m in SyncMode}:
            raise ValueError(f"Unknown sync mode: {self.mode!r}")
        runner = getattr(self, f"_run_{self.mode}", None)

        if not callable(runner):
            self._mark_failed(ValueError(f"No handler for mode: {self.mode!r}"))
            return

        with self._run_guard():
            runner()

    def _prepare_failure_vals(self, error: Exception) -> "odoo.values.shopify_sync":
        tb = traceback.format_exc()
        vals: "odoo.values.shopify_sync" = {
            "end_time": fields.Datetime.now(),
            "error_message": str(error),
            "error_exception": error.__class__.__name__,
            "error_traceback": tb,
        }

        should_retry = self.retry_attempts < self.MAX_RETRY_ATTEMPTS and isinstance(error, self.RETRYABLE_ERRORS)
        if should_retry:
            sleep(self.retry_attempts)
            vals["state"] = "queued"
            vals["retry_attempts"] = self.retry_attempts + 1
            _logger.warning(
                f"Scheduling retry {vals['retry_attempts']}/{self.MAX_RETRY_ATTEMPTS} for Shopify sync {self.id} ({self.mode})",
            )
        else:
            vals["state"] = "failed"

            self.notify_channel_on_error(
                f"Shopify sync failed",
                vals["error_message"],
                self.error_odoo_record,
                self.error_shopify_record or self.error_shopify_input,
            )

        return vals

    def _mark_failed(self, error: Exception) -> None:
        def _truncate_text(text: str) -> str:
            if len(text) > 100000:
                return text[:50000] + f"...{len(text) - 50000}"
            return text

        vals = self._prepare_failure_vals(error)

        if hasattr(error, "odoo_record") and isinstance(error.odoo_record, models.Model):
            vals["error_odoo_record"] = error.odoo_record

        if hasattr(error, "shopify_record") and isinstance(error.shopify_record, BaseModel):
            vals["error_shopify_record"] = error.shopify_record.model_dump(exclude_none=True, mode="json")

        if hasattr(error, "shopify_input") and isinstance(error.shopify_input, BaseModel):
            vals["error_shopify_input"] = error.shopify_input.model_dump(exclude_none=True, mode="json")

        if hasattr(error, "errors"):
            raw_errors = error.errors() if callable(error.errors) else error.errors
            try:
                errors = list(raw_errors)
            except TypeError:
                errors = [raw_errors]
            combined = "\n".join(map(str, errors))
            vals["error_shopify_record"] = _truncate_text(f"{vals.get('error_shopify_record', '')}\n{combined}".strip())

        self.write(vals)
        self._safe_commit()
        _logger.error(f"Shopify sync failed:\n{vals['error_traceback']}")

    @contextmanager
    def _run_guard(self) -> Generator[None, None, None]:
        self.write({"state": "running"})
        self._safe_commit()
        try:
            yield
            self.state = "success"
            resource_type = SyncMode(self.mode).resource_type
            if resource_type and self.last_import_start_time:
                config_key = last_import_config_key(resource_type)
                self.env["ir.config_parameter"].set_param(config_key, format_datetime_for_shopify(self.last_import_start_time))
            self._safe_commit()
        except Exception as error:
            self._safe_rollback()
            self._mark_failed(error)
            self._safe_commit()
            raise ShopifySyncRunFailed()
        finally:
            self.end_time = fields.Datetime.now()
            try:
                self._safe_commit()
            except (SerializationFailure, InFailedSqlTransaction, TransactionRollbackError):
                _logger.debug("Final commit failed due to transaction state, rolling back")
                self._safe_rollback()

    @property
    def completed_str(self) -> str:
        return f"{self.updated_count} of {self.total_count} product(s)"

    def _run_reset_shopify(self) -> None:
        from ..services.shopify import ProductDeleter

        deleter = ProductDeleter(self.env, self)
        deleter.delete_all_products()

        products = self.env["product.product"].search([])
        products.shopify_next_export = False
        products.shopify_last_exported_at = False
        products.shopify_next_export_quantity_change_amount = 0
        products.shopify_created_at = False
        system = self.env["external.system"].search([("code", "=", "shopify")], limit=1)
        if system:
            external_ids = (
                self.env["external.id"].sudo().with_context(active_test=False).search([("system_id", "=", system.id)])
            )
            if external_ids:
                external_ids.write({"active": False})
                external_ids.unlink()

        self._safe_commit()

        self.total_count = max(len(products), self.total_count)

    def _run_import_all_products(self) -> None:
        _logger.info("Importing all products from Shopify")
        from ..services.shopify import ProductImporter

        self.last_import_start_time = fields.Datetime.now()
        importer = ProductImporter(self.env, self)
        importer.run()

    def _run_export_all_products(self) -> None:
        _logger.info("Exporting all products to Shopify")
        from ..services.shopify import ProductExporter

        exporter = ProductExporter(self.env, self)
        exporter.export_products_since_datetime(DEFAULT_DATETIME)

    def _run_import_then_export_products(self) -> None:
        self._run_import_changed_products()

        self.env["shopify.sync"].create({"mode": SyncMode.EXPORT_CHANGED_PRODUCTS.value, "state": "queued"})

    def _run_import_changed_products(self) -> None:
        _logger.info("Importing changed products from Shopify")
        from ..services.shopify import ProductImporter

        self.last_import_start_time = fields.Datetime.now()
        importer = ProductImporter(self.env, self)
        importer.import_products_since_last_import()

    def _run_export_changed_products(self) -> None:
        _logger.info("Exporting changed products to Shopify")
        from ..services.shopify import ProductExporter

        exporter = ProductExporter(self.env, self)
        exporter.export_products_since_last_export()

    def _run_import_one_product(self) -> None:
        _logger.info("Importing one product from Shopify")
        from ..services.shopify import ProductImporter

        importer = ProductImporter(self.env, self)
        importer.run_by_id(self.shopify_product_id_to_sync)

    def _run_export_batch_products(self) -> None:
        _logger.info("Exporting batch of products to Shopify")
        from ..services.shopify import ProductExporter

        exporter = ProductExporter(self.env, self)
        exporter.export_products(self.odoo_products_to_sync)

    def _run_import_products_since_date(self) -> None:
        _logger.info("Importing products from Shopify since a specific date")
        from ..services.shopify import ProductImporter

        importer = ProductImporter(self.env, self)
        if not self.datetime_to_sync:
            raise ValueError("Datetime to sync is not set.")
        filter_query = f'updated_at:>"{format_datetime_for_shopify(self.datetime_to_sync)}"'
        importer.run(query=filter_query)

    def _run_export_products_since_date(self) -> None:
        _logger.info("Exporting products to Shopify since a specific date")
        from ..services.shopify import ProductExporter

        if not self.datetime_to_sync:
            raise ValueError("Datetime to sync is not set.")

        exporter = ProductExporter(self.env, self)
        exporter.export_products_since_datetime(self.datetime_to_sync)

    def _run_import_all_orders(self) -> None:
        _logger.info("Importing all orders from Shopify")
        from ..services.shopify import OrderImporter

        self.last_import_start_time = fields.Datetime.now()
        importer = OrderImporter(self.env, self)
        importer.run()

    def _run_import_changed_orders(self) -> None:
        _logger.info("Importing changed orders from Shopify")
        from ..services.shopify import OrderImporter

        self.last_import_start_time = fields.Datetime.now()
        importer = OrderImporter(self.env, self)
        importer.import_orders_since_last_import()

    def _run_import_one_order(self) -> None:
        _logger.info("Importing one order from Shopify")
        from ..services.shopify import OrderImporter

        importer = OrderImporter(self.env, self)
        importer.run_by_id(self.shopify_product_id_to_sync)

    def _run_import_all_customers(self) -> None:
        _logger.info("Importing all customers from Shopify")
        from ..services.shopify import CustomerImporter

        self.last_import_start_time = fields.Datetime.now()
        importer = CustomerImporter(self.env, self)
        importer.run()

    def _run_import_changed_customers(self) -> None:
        _logger.info("Importing changed customers from Shopify")
        from ..services.shopify import CustomerImporter

        self.last_import_start_time = fields.Datetime.now()
        importer = CustomerImporter(self.env, self)
        importer.import_customers_since_last_import()

    def _run_import_one_customer(self) -> None:
        _logger.info("Importing one customer from Shopify")
        from ..services.shopify import CustomerImporter

        importer = CustomerImporter(self.env, self)
        importer.run_by_id(self.shopify_product_id_to_sync)
