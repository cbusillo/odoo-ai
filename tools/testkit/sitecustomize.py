import hashlib
import inspect
import json
import logging
import os
import threading
import unittest
from collections.abc import Iterable
from functools import wraps

_logger = logging.getLogger(__name__)

DEFAULT_BROWSER_READY = "window.odoo && odoo.registry && odoo.registry.category"
WEB_READY_CHECK = (
    'Boolean(window.odoo?.__DEBUG__?.services || window.odoo?.loader?.modules?.get("@web/core/registry")?.registry?.category)'
)
DEFAULT_CURSOR_LOCK_TIMEOUT_SECONDS = 120
_WARMED_DBS: set[str] = set()
_WARMED_LOCK = threading.Lock()
_TOUR_MODULE_CACHE: dict[str, str] = {}
_TOUR_MODULE_LOCK = threading.Lock()


def _slicer_enabled() -> bool:
    return os.environ.get("OAI_TEST_SLICER", "0") == "1"


def _parse_slicer_modules() -> set[str]:
    raw_value = os.environ.get("TEST_SLICE_MODULES", "").strip()
    if not raw_value:
        return set()
    return {module_name.strip() for module_name in raw_value.split(",") if module_name.strip()}


def _bucket_of(name: str, total: int) -> int:
    if total <= 1:
        return 0
    hash_value = hashlib.sha1(name.encode()).hexdigest()
    return int(hash_value[:8], 16) % total


def _matches_target_module(python_module: str, targets: Iterable[str]) -> bool:
    if not targets:
        return True
    # Typical Odoo test module path: odoo.addons.<module>....
    for target in targets:
        needle = f".addons.{target}."
        if needle in python_module or python_module.endswith(f".addons.{target}") or python_module.startswith(f"{target}."):
            return True
    return False


def _install_unittest_slicer(total: int, index: int, only_modules: set[str]) -> None:
    original_getter = unittest.TestLoader.getTestCaseNames

    def sliced_get(
        self: unittest.TestLoader,
        test_case_class: type[unittest.TestCase],
    ) -> list[str]:  # type: ignore[override]
        names: list[str] = list(original_getter(self, test_case_class))
        # Only slice targeted addon modules; otherwise leave untouched
        python_module = getattr(test_case_class, "__module__", "")
        if not _matches_target_module(python_module, only_modules):
            return names

        selected_names: list[str] = []
        class_name = getattr(test_case_class, "__name__", "Test")
        for test_name in names:
            if not test_name.startswith("test"):
                # do not slice non-tests
                selected_names.append(test_name)
                continue
            bucket_key = f"{python_module}.{class_name}.{test_name}"
            if _bucket_of(bucket_key, total) == index:
                selected_names.append(test_name)
        return selected_names

    unittest.TestLoader.getTestCaseNames = sliced_get  # type: ignore[assignment]


def _install_odoo_loader_slicer(total: int, index: int, only_modules: set[str]) -> None:
    try:
        import odoo.tests.loader as loader
    except Exception as error:
        _logger.debug("slicer: failed to import odoo.tests.loader (%s)", error)
        return

    original_getter = getattr(loader, "get_module_test_cases", None)
    if original_getter is None:
        return

    def sliced_get_module_test_cases(module: object) -> Iterable[unittest.TestCase]:
        for test_case_instance in original_getter(module):
            test_case_class = test_case_instance.__class__
            python_module = getattr(test_case_class, "__module__", "")
            if not _matches_target_module(python_module, only_modules):
                yield test_case_instance
                continue

            class_name = getattr(test_case_class, "__name__", "Test")
            method_name = getattr(test_case_instance, "_testMethodName", "")
            if not method_name:
                yield test_case_instance
                continue
            bucket_key = f"{python_module}.{class_name}.{method_name}"
            if _bucket_of(bucket_key, total) == index:
                yield test_case_instance

    loader.get_module_test_cases = sliced_get_module_test_cases


def _apply_test_slicer() -> None:
    if not _slicer_enabled():
        return
    try:
        total = int(os.environ.get("TEST_SLICE_TOTAL", "0"))
        index = int(os.environ.get("TEST_SLICE_INDEX", "0"))
    except ValueError:
        return
    if total <= 1 or index < 0 or index >= total:
        return
    only_modules = _parse_slicer_modules()
    _install_unittest_slicer(total, index, only_modules)
    _install_odoo_loader_slicer(total, index, only_modules)


def _coerce_int(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _ensure_test_cursor_timeout() -> None:
    try:
        from odoo.tests.common import BaseCase
    except Exception as error:
        _logger.debug("sitecustomize: failed to import BaseCase (%s)", error)
        return

    if not hasattr(BaseCase, "test_cursor_lock_timeout"):
        return

    current_value = getattr(BaseCase, "test_cursor_lock_timeout", None)
    current_timeout = _coerce_int(current_value, 0)
    if current_timeout >= DEFAULT_CURSOR_LOCK_TIMEOUT_SECONDS:
        return

    BaseCase.test_cursor_lock_timeout = DEFAULT_CURSOR_LOCK_TIMEOUT_SECONDS


def _append_db_param(url: str, db_name: str) -> str:
    if "db=" in url:
        return url
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["db"] = db_name
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _warm_tour_assets(case: object) -> None:
    env = getattr(case, "env", None)
    cr = getattr(env, "cr", None) if env else None
    db_name = getattr(cr, "dbname", None)
    if not db_name:
        _logger.debug("sitecustomize: warmup skipped (db name unavailable)")
        return
    with _WARMED_LOCK:
        if db_name in _WARMED_DBS:
            return
        _WARMED_DBS.add(db_name)

    http_port = getattr(case, "http_port", None)
    if not callable(http_port):
        return
    try:
        port = http_port()
    except Exception as error:
        _logger.debug("sitecustomize: warmup skipped (http_port unavailable: %s)", error)
        return
    if not port:
        return
    try:
        import requests
    except Exception as error:
        _logger.debug("sitecustomize: warmup skipped (requests unavailable: %s)", error)
        return

    base = f"http://127.0.0.1:{port}"
    urls = (
        _append_db_param(base + "/web", db_name),
        _append_db_param(base + "/web/tests?headless=1", db_name),
        _append_db_param(base + "/web/webclient/version_info", db_name),
        _append_db_param(base + "/web/webclient/translations?lang=en_US", db_name),
    )
    for warm_url in urls:
        try:
            requests.get(warm_url, timeout=30)
        except Exception as error:
            _logger.debug("sitecustomize: warmup request failed (%s): %s", warm_url, error)


def _build_tour_ready_expression(tour_name: str, module_name: str | None) -> str:
    escaped = json.dumps(tour_name)
    module_literal = json.dumps(module_name) if module_name else "null"
    return (
        "(async () => {"
        "if (window.odoo && odoo.isTourReady) {"
        f"try {{ return await odoo.isTourReady({escaped}); }} catch (error) {{}}"
        "}"
        'const assets = window.odoo?.loader?.modules?.get("@web/core/assets");'
        "if (assets?.loadBundle) {"
        'try { await assets.loadBundle("web.__assets_tests_call__", { css: false }); } catch (error) {}'
        'try { await assets.loadBundle("web.assets_tests", { css: false }); } catch (error) {}'
        "}"
        "const loader = window.odoo?.loader;"
        f"const moduleName = {module_literal};"
        "if (loader?.factories?.has(moduleName) && !loader.modules?.has(moduleName)) {"
        "try { loader.startModule(moduleName); } catch (error) {}"
        "}"
        "if (window.odoo && odoo.isTourReady) {"
        f"try {{ return await odoo.isTourReady({escaped}); }} catch (error) {{}}"
        "}"
        "return false;"
        "})()"
    )


def _build_web_ready_expression() -> str:
    return (
        "(async () => {"
        'const assets = window.odoo?.loader?.modules?.get("@web/core/assets");'
        "if (assets?.loadBundle) {"
        'try { await assets.loadBundle("web.assets_web", { css: false }); } catch (error) {}'
        'try { await assets.loadBundle("web.assets_tests", { css: false }); } catch (error) {}'
        "}"
        f"return {WEB_READY_CHECK};"
        "})()"
    )


def _resolve_tour_module_name(case: object, tour_name: str) -> str | None:
    with _TOUR_MODULE_LOCK:
        cached = _TOUR_MODULE_CACHE.get(tour_name)
    if cached:
        return cached

    env = getattr(case, "env", None)
    if env is None:
        return None
    try:
        from odoo.tools.js_transpiler import url_to_module_path
        from odoo.tools.misc import file_open
    except Exception as error:
        _logger.debug("sitecustomize: tour module resolve skipped (%s)", error)
        return None

    try:
        assets_params = env["ir.asset"]._get_asset_params()
        asset_paths = env["ir.asset"]._get_asset_paths("web.assets_tests", assets_params)
    except Exception as error:
        _logger.debug("sitecustomize: tour module resolve failed (%s)", error)
        return None

    needle_variants = (
        f'registry.category("web_tour.tours").add("{tour_name}"',
        f"registry.category('web_tour.tours').add('{tour_name}'",
    )
    for url_path, _full_path, _bundle, _modified in asset_paths:
        if "/static/tests/tours/" not in url_path:
            continue
        try:
            with file_open(url_path.lstrip("/"), "rb") as handle:
                content = handle.read().decode("utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        if any(needle in content for needle in needle_variants):
            module_name = url_to_module_path(url_path)
            with _TOUR_MODULE_LOCK:
                _TOUR_MODULE_CACHE[tour_name] = module_name
            return module_name
    return None


def _wrap_start_tour(http_case: type[object]) -> None:
    original = getattr(http_case, "start_tour", None)
    if original is None:
        return

    @wraps(original)
    def wrapper(self: object, *args: object, **kwargs: object) -> object:
        _warm_tour_assets(self)
        if not kwargs.get("ready"):
            tour_name = None
            if len(args) > 1:
                tour_name = args[1]
            elif "tour_name" in kwargs:
                tour_name = kwargs["tour_name"]
            if tour_name:
                module_name = _resolve_tour_module_name(self, str(tour_name))
                kwargs["ready"] = _build_tour_ready_expression(str(tour_name), module_name)
        return original(self, *args, **kwargs)

    http_case.start_tour = wrapper


def _wrap_browser_js(http_case: type[object]) -> None:
    original = getattr(http_case, "browser_js", None)
    if original is None:
        return

    try:
        signature = inspect.signature(original)
    except (TypeError, ValueError):
        signature = None

    @wraps(original)
    def wrapper(self: object, *args: object, **kwargs: object) -> object:
        ready_value = None
        ready_in_kwargs = "ready" in kwargs
        ready_index = None
        url_path_value = None
        code_value = None
        code_in_kwargs = "code" in kwargs
        code_index = None
        bound = None
        mutable_args = list(args)
        if signature and "ready" in signature.parameters:
            try:
                bound = signature.bind_partial(self, *args, **kwargs)
            except TypeError:
                bound = None
            if bound:
                ready_value = bound.arguments.get("ready")
                url_path_value = bound.arguments.get("url_path")
                code_value = bound.arguments.get("code")
            try:
                params = list(signature.parameters)
                ready_index = params.index("ready") - 1
                code_index = params.index("code") - 1
            except ValueError:
                ready_index = None
                code_index = None
        if url_path_value is None and mutable_args:
            url_path_value = mutable_args[0]
        if code_value is None and code_index is not None and 0 <= code_index < len(mutable_args):
            code_value = mutable_args[code_index]

        def _set_ready(value: str) -> None:
            if ready_in_kwargs:
                kwargs["ready"] = value
            elif ready_index is not None and 0 <= ready_index < len(mutable_args):
                mutable_args[ready_index] = value
            else:
                kwargs["ready"] = value

        def _set_code(value: str) -> None:
            if code_in_kwargs:
                kwargs["code"] = value
            elif code_index is not None and 0 <= code_index < len(mutable_args):
                mutable_args[code_index] = value
            else:
                kwargs["code"] = value

        if isinstance(url_path_value, str) and url_path_value.startswith("/web"):
            env = getattr(self, "env", None)
            cr = getattr(env, "cr", None) if env else None
            db_name = getattr(cr, "dbname", None)
            if db_name:
                updated_url = _append_db_param(url_path_value, db_name)
                if updated_url != url_path_value:
                    if "url_path" in kwargs:
                        kwargs["url_path"] = updated_url
                    elif mutable_args:
                        mutable_args[0] = updated_url

        ready_text = str(ready_value).strip() if ready_value else ""
        if isinstance(code_value, str) and "web_tour.tours" in code_value:
            timeout_value = None
            if signature and bound:
                timeout_value = bound.arguments.get("timeout")
            if timeout_value is None:
                timeout_value = kwargs.get("timeout")
            try:
                timeout_int = int(timeout_value) if timeout_value is not None else 60
            except (TypeError, ValueError):
                timeout_int = 60
            wait_ms = max(1000, timeout_int * 1000)
            wrapped_code = (
                "(async () => {"
                f"const deadline = Date.now() + {wait_ms};"
                "while (Date.now() < deadline) {"
                f"if ({WEB_READY_CHECK}) {{ break; }}"
                "await new Promise(resolve => setTimeout(resolve, 200));"
                "}"
                f"if (!({WEB_READY_CHECK})) {{"
                "throw new Error('testkit: odoo registry not ready');"
                "}"
                f"{code_value}"
                "})()"
            )
            if not ready_value or ready_text == DEFAULT_BROWSER_READY:
                _set_ready(_build_web_ready_expression())
            _warm_tour_assets(self)
            _set_code(wrapped_code)
            return original(self, *mutable_args, **kwargs)
        if not ready_value:
            _warm_tour_assets(self)
            _set_ready(_build_web_ready_expression())
        elif ready_text == DEFAULT_BROWSER_READY:
            _warm_tour_assets(self)
            _set_ready(_build_web_ready_expression())
        return original(self, *mutable_args, **kwargs)

    http_case.browser_js = wrapper


def _apply_patches() -> None:
    try:
        _apply_test_slicer()
    except (AttributeError, RuntimeError, TypeError, ValueError) as error:
        _logger.debug("slicer: init failed (%s)", error)

    _ensure_test_cursor_timeout()

    try:
        from odoo.tests.common import HttpCase
    except Exception as error:
        _logger.debug("sitecustomize: failed to import HttpCase (%s)", error)
        return
    _wrap_browser_js(HttpCase)
    _wrap_start_tour(HttpCase)
    try:
        from odoo.tests import common as tests_common
    except Exception as error:
        _logger.debug("sitecustomize: failed to patch Browser throttle (%s)", error)
    else:
        browser_class = getattr(tests_common, "Browser", None)
        if browser_class:
            current = getattr(browser_class, "throttling_factor", 1)
            browser_class.throttling_factor = max(float(current), 2.0)


_apply_patches()
