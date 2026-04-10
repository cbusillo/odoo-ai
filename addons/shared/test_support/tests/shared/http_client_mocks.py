from collections.abc import Callable
from typing import Any

from httpx import Request, Response


class DummyHttpClient:
    """Simple httpx-compatible client double used in tests."""

    def __init__(self, **kwargs: Any) -> None:
        self.event_hooks = kwargs.get("event_hooks", {})
        self.send_calls: list[Request] = []
        self.response = Response(200, request=Request("GET", "http://t"))

    def send(self, request: Request, **_kwargs: Any) -> Response:
        self.send_calls.append(request)
        return self.response


def build_dummy_http_client(
    *,
    send_callback: Callable[[DummyHttpClient, Request], Response | Any] | None = None,
    init_callback: Callable[[DummyHttpClient], None] | None = None,
) -> type[DummyHttpClient]:
    """Create a ``DummyHttpClient`` subclass with custom send/init behavior."""

    class CustomDummyHttpClient(DummyHttpClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            if init_callback is not None:
                init_callback(self)

        def send(self, request: Request, **_kwargs: Any) -> Response | Any:
            self.send_calls.append(request)
            if send_callback is None:
                return self.response
            return send_callback(self, request)

    return CustomDummyHttpClient


__all__ = ["DummyHttpClient", "build_dummy_http_client"]
