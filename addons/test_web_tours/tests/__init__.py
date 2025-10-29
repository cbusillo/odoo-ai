import sys

try:
    from . import tour as _tour
except ImportError:
    _tour = None
else:
    for _name in dir(_tour):
        if _name.startswith("test_"):
            sys.modules[__name__].__dict__[_name] = getattr(_tour, _name)
