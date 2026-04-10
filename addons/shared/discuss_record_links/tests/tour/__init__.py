# Only expose the smoke tour by default; legacy tours require additional data setup
from . import test_smoke_login_tour

__all__ = ["test_smoke_login_tour"]
