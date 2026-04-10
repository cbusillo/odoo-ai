import sys

from .minimal_common_imports import build_addon_test_api, build_common_imports

try:
    from . import tour as _tour
except ImportError:
    _tour = None
else:
    for _name in dir(_tour):
        if _name.startswith("test_"):
            sys.modules[__name__].__dict__[_name] = getattr(_tour, _name)


__all__ = ["build_addon_test_api", "build_common_imports"]
