from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from httpx import Request, Response
from test_support.tests.shared.http_client_mocks import DummyHttpClient, build_dummy_http_client
from test_support.tests.shared.sync_doubles import DummySyncRecord

from ..common_imports import common

from ...services.shopify.service import ShopifyService
from ...services.shopify import service as _service_module
from ...services.shopify.helpers import ShopifyApiError
from ..fixtures.base import IntegrationTestCase

@common.tagged(*common.INTEGRATION_TAGS)
class TestShopifyService(IntegrationTestCase):
    @dataclass
    class SendFuncState:
        send_function: Callable[[Request], Any]

    @dataclass
    class AttemptState:
        attempt_count: int = 0

    @dataclass
    class RequestCountState:
        request_count: int = 0

    @dataclass
    class ConcurrentRequestState:
        concurrent_request_count: int = 0
        max_concurrent_request_count: int = 0

    def setUp(self) -> None:
        super().setUp()

    def _service(self) -> ShopifyService:
        return ShopifyService(self.env, DummySyncRecord())

    def _build_send_func_dummy_client(
        self,
        response_factory: Callable[[Request], Any],
        *,
        initialize_dummy_http_client: Callable[[DummyHttpClient], None] | None = None,
    ) -> tuple[type[DummyHttpClient], SendFuncState]:
        state = self.SendFuncState(send_function=response_factory)

        def initialize_http_client(dummy_http_client: DummyHttpClient) -> None:
            if initialize_dummy_http_client:
                initialize_dummy_http_client(dummy_http_client)

        def send_with_stored_factory(_dummy_http_client: DummyHttpClient, request: Request) -> Response:
            return state.send_function(request)

        return (
            build_dummy_http_client(
                init_callback=initialize_http_client,
                send_callback=send_with_stored_factory,
            ),
            state,
        )

    def _build_attempt_tracking_dummy_client(
        self,
        response_factory_for_attempt: Callable[[int, Request], Response],
    ) -> tuple[type[DummyHttpClient], AttemptState]:
        state = self.AttemptState()

        def send_response_for_attempt(_dummy_http_client: DummyHttpClient, request: Request) -> Response:
            state.attempt_count += 1
            return response_factory_for_attempt(state.attempt_count, request)

        return (
            build_dummy_http_client(
                send_callback=send_response_for_attempt,
            ),
            state,
        )

    @staticmethod
    def _assert_dummy_http_client(
        client: object,
        expected_client_class: type[DummyHttpClient],
        *,
        error_message: str,
    ) -> DummyHttpClient:
        if not isinstance(client, expected_client_class):
            raise AssertionError(error_message)
        return client

    @contextmanager
    def _client(self, service: ShopifyService, client_cls: type[DummyHttpClient]) -> Iterator[tuple[DummyHttpClient, common.MagicMock]]:
        with common.patch.object(_service_module, "Client", client_cls), common.patch.object(_service_module, "sleep") as fake_sleep:
            client = service._create_http_client("t")
            if not isinstance(client, DummyHttpClient):
                raise AssertionError("HTTP client was not constructed as DummyHttpClient")
            yield client, fake_sleep

    def _test_client_retry_behavior(self, service: ShopifyService, client_cls: type[DummyHttpClient], expected_calls: int):
        with self._client(service, client_cls) as (client, fake_sleep):
            req = Request("GET", "http://t")
            result = client.send(req)

            self.assertEqual(result.status_code, 200)
            self.assertEqual(len(client.send_calls), expected_calls)
            fake_sleep.assert_called()

    def test_compute_throttle_delay_none(self) -> None:
        service = self._service()
        self.assertIsNone(service._compute_throttle_delay({}))

    def test_compute_throttle_delay_zero(self) -> None:
        service = self._service()
        data = {"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": service.MIN_API_POINTS}}}}
        self.assertEqual(service._compute_throttle_delay(data), 0.0)

    def test_compute_throttle_delay_bounds(self) -> None:
        service = self._service()
        data = {"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 100, "restoreRate": 25}}}}
        self.assertEqual(service._compute_throttle_delay(data), 16.0)
        data = {"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 0, "restoreRate": 0}}}}
        self.assertEqual(service._compute_throttle_delay(data), 60.0)
        data = {"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": service.MIN_API_POINTS - 1, "restoreRate": 1000}}}}
        self.assertEqual(service._compute_throttle_delay(data), 1.0)

    def test_throttle_info_with_error(self) -> None:
        service = self._service()
        data = {
            "errors": [{"extensions": {"code": "THROTTLED"}}],
            "extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 400, "restoreRate": 10}}},
        }
        self.assertEqual(service._throttle_info(data), (True, 10.0))

    def test_throttle_info_without_error(self) -> None:
        service = self._service()
        data = {"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 499, "restoreRate": 1000}}}}
        self.assertEqual(service._throttle_info(data), (False, 1.0))

    def test_get_first_location_gid(self) -> None:
        service = self._service()

        class Loc:
            def __init__(self, gid: str) -> None:
                self.id = gid

        class LocationsResponse:
            def __init__(self, nodes: list[Loc]) -> None:
                self.nodes = nodes

        service._client = type(
            "LocationsClient",
            (),
            {"get_locations": lambda _client: LocationsResponse([Loc("gid1")])},
        )()
        self.assertEqual(service.get_first_location_gid(), "gid1")

    def test_get_first_location_gid_error(self) -> None:
        service = self._service()
        service._client = type(
            "LocationsClient",
            (),
            {"get_locations": lambda _client: type("LocationsResponse", (), {"nodes": []})()},
        )()
        with self.assertRaises(Exception):
            service.get_first_location_gid()

    def test_create_client_success_and_retry(self) -> None:
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("shopify.shop_url_key", "shop")
        config.set_param("shopify.api_token", "token")
        service = self._service()

        def initialize_dummy_http_client(dummy_http_client: DummyHttpClient) -> None:
            dummy_http_client.event_hooks = {}

        dummy_client_class, send_func_state = self._build_send_func_dummy_client(
            lambda request: Response(200, request=request, json={}),
            initialize_dummy_http_client=initialize_dummy_http_client,
        )

        req = Request("GET", "http://t")
        responses = [Response(200, request=req, json={}), Response(200, request=req, json={})]

        def send_one(_request: Request) -> Response:
            return responses.pop(0)

        with (
            common.patch.object(_service_module, "Client", dummy_client_class),
            common.patch.object(_service_module, "ShopifyClient", lambda http_client, url: http_client),
            common.patch.object(_service_module, "sleep") as fake_sleep,
            common.patch.object(service, "get_first_location_gid", return_value="loc"),
            common.patch.object(service, "_throttle_info", side_effect=[(True, None), (False, None)]),
        ):
            client = service._create_client()
            dummy_client = self._assert_dummy_http_client(
                client,
                dummy_client_class,
                error_message="Client was not constructed as DummyHttpClient",
            )
            self.assertIs(service._client, client)
            send_func_state.send_function = send_one
            result = dummy_client.send(req)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(len(dummy_client.send_calls), 2)
            fake_sleep.assert_called_with(1.0)
            self.assertEqual(service.sync_record.hard_throttle_count, 1)

    def test_create_client_missing_credentials(self) -> None:
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("shopify.shop_url_key", "")
        service = self._service()
        with self.assertRaises(Exception):
            service._create_client()

    def test_create_client_resets_on_location_error(self) -> None:
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("shopify.shop_url_key", "shop")
        config.set_param("shopify.api_token", "token")
        service = self._service()

        with common.patch.object(service, "get_first_location_gid", side_effect=ShopifyApiError("boom")):
            with self.assertRaises(ShopifyApiError):
                service._create_client()
        self.assertIsNone(service._client)

    def test_client_property_creates_client(self) -> None:
        service = self._service()
        mock_client = common.MagicMock()

        def create_client() -> common.MagicMock:
            service._client = mock_client
            return mock_client

        with common.patch.object(service, "_create_client", side_effect=create_client) as create:
            service._client = None
            self.assertEqual(service.client, mock_client)
            create.assert_called_once()

    def test_get_first_location_gid_no_id(self) -> None:
        service = self._service()

        class Loc:
            id = None

        class Res:
            nodes = [Loc()]

        service._client = type("C", (), {"get_locations": lambda _: Res()})()
        with self.assertRaises(Exception):
            service.get_first_location_gid()

    def test_rate_limit_hook_waits(self) -> None:
        service = self._service()

        dummy_client_class, _send_func_state = self._build_send_func_dummy_client(
            lambda request: Response(200, request=request, json={}),
        )

        class FakeResponse:
            def __init__(self, json_data: dict) -> None:
                self.headers = {"content-type": "application/json"}
                self.status_code = 200
                self._json = json_data
                self.is_closed = False
                self.read_called = False
                self.request = Request("GET", "http://t")

            def read(self) -> None:
                self.read_called = True
                self.is_closed = True

            def json(self) -> dict:
                return self._json

            def close(self) -> None:
                self.is_closed = True

        with common.patch.object(_service_module, "Client", dummy_client_class), common.patch.object(_service_module, "sleep") as fake_sleep:
            client = service._create_http_client("t")
            hook = client.event_hooks["response"][0]
            resp = FakeResponse({"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 100, "restoreRate": 2}}}})
            hook(resp)
            self.assertTrue(resp.read_called)
            fake_sleep.assert_called_once()

    def test_send_with_retry_transient_error(self) -> None:
        service = self._service()

        dummy_client_class, _send_func_state = self._build_send_func_dummy_client(
            lambda request: Response(500, request=request),
        )

        with self._client(service, dummy_client_class) as (client, fake_sleep):
            service.MAX_RETRY_ATTEMPTS = 1
            req = Request("GET", "http://t")
            with self.assertRaises(Exception):
                client.send(req)
            self.assertEqual(len(client.send_calls), 2)
            fake_sleep.assert_called()

    def _test_send_without_retry(self, response_factory: Callable[[Request], Response | object]) -> None:
        service = self._service()

        dummy_client_class = build_dummy_http_client(
            init_callback=lambda dummy_http_client: setattr(
                dummy_http_client,
                "response",
                response_factory(Request("GET", "http://t")),
            ),
        )

        with self._client(service, dummy_client_class) as (client, fake_sleep):
            req = Request("GET", "http://t")
            result = client.send(req)
            self.assertIs(result, client.response)
            self.assertEqual(len(client.send_calls), 1)
            fake_sleep.assert_not_called()

    def test_send_with_retry_not_transient(self) -> None:
        def create_response(request: Request) -> Response:
            return Response(
                404,
                headers={"content-type": "application/json"},
                request=request,
            )

        self._test_send_without_retry(create_response)

    def test_send_with_retry_invalid_json(self) -> None:
        def create_response(_request: Request) -> object:
            class Resp:
                status_code = 200
                headers = {"content-type": "application/json"}

                def json(self) -> dict:
                    raise ValueError("bad")

                def close(self) -> None:
                    pass

            return Resp()

        self._test_send_without_retry(create_response)

    def test_rate_limit_hook_no_json(self) -> None:
        service = self._service()

        dummy_client_class = build_dummy_http_client(
            send_callback=lambda _client, request: Response(200, request=request),
        )

        class Resp:
            headers: dict[str, str] = {}

        with common.patch.object(_service_module, "Client", dummy_client_class), common.patch.object(_service_module, "sleep") as fake_sleep:
            client = service._create_http_client("t")
            hook = client.event_hooks["response"][0]
            hook(Resp())
            fake_sleep.assert_not_called()

    def test_rate_limit_hook_closed_or_no_wait(self) -> None:
        service = self._service()

        dummy_client_class = build_dummy_http_client(
            send_callback=lambda _client, request: Response(200, request=request),
        )

        class Resp:
            def __init__(self, data: dict, closed: bool) -> None:
                self.headers = {"content-type": "application/json"}
                self._json = data
                self.is_closed = closed
                self.read_called = False
                self.request = Request("GET", "http://t")

            def read(self) -> None:
                self.read_called = True
                self.is_closed = True

            def json(self) -> dict:
                return self._json

            def close(self) -> None:
                self.is_closed = True

        with common.patch.object(_service_module, "Client", dummy_client_class), common.patch.object(_service_module, "sleep") as fake_sleep:
            client = service._create_http_client("t")
            hook = client.event_hooks["response"][0]
            resp_closed = Resp({}, True)
            hook(resp_closed)
            self.assertFalse(resp_closed.read_called)

            resp_ok = Resp(
                {"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": service.MIN_API_POINTS, "restoreRate": 1}}}},
                False,
            )
            hook(resp_ok)
            fake_sleep.assert_not_called()

    def test_send_with_retry_zero_attempts(self) -> None:
        service = self._service()
        service.MAX_RETRY_ATTEMPTS = -1

        dummy_client_class = build_dummy_http_client(
            send_callback=lambda _client, request: Response(200, request=request),
        )

        with common.patch.object(_service_module, "Client", dummy_client_class), common.patch.object(_service_module, "sleep") as fake_sleep:
            client = service._create_http_client("t")
            req = Request("GET", "http://t")
            with self.assertRaises(ShopifyApiError):
                client.send(req)
            fake_sleep.assert_not_called()

    def test_rate_limit_progressive_backoff(self) -> None:
        service = self._service()

        def response_for_attempt(attempt_count: int, request: Request) -> Response:
            if attempt_count < 3:
                return Response(
                    429,
                    json={"errors": [{"extensions": {"code": "THROTTLED"}}]},
                    request=request,
                    headers={"content-type": "application/json"},
                )
            return Response(200, json={}, request=request)

        dummy_client_class, _attempt_state = self._build_attempt_tracking_dummy_client(response_for_attempt)

        service.MAX_RETRY_ATTEMPTS = 3
        with self._client(service, dummy_client_class) as (client, fake_sleep):
            req = Request("GET", "http://t")
            result = client.send(req)

            self.assertEqual(result.status_code, 200)
            self.assertEqual(len(client.send_calls), 3)
            calls = fake_sleep.call_args_list
            self.assertGreater(len(calls), 1)
            for i in range(1, len(calls)):
                self.assertGreaterEqual(calls[i][0][0], calls[i - 1][0][0])

    def test_concurrent_request_handling(self) -> None:
        service = self._service()

        concurrent_request_state = self.ConcurrentRequestState()

        def send_response(_dummy_http_client: DummyHttpClient, request: Request) -> Response:
            concurrent_request_state.concurrent_request_count += 1
            concurrent_request_state.max_concurrent_request_count = max(
                concurrent_request_state.max_concurrent_request_count,
                concurrent_request_state.concurrent_request_count,
            )
            response = Response(200, json={}, request=request)
            concurrent_request_state.concurrent_request_count -= 1
            return response

        dummy_client_class = build_dummy_http_client(
            send_callback=send_response,
        )

        with self._client(service, dummy_client_class) as (client, _):
            for _ in range(5):
                req = Request("GET", "http://t")
                client.send(req)

            self.assertEqual(len(client.send_calls), 5)
            self.assertEqual(concurrent_request_state.max_concurrent_request_count, 1)

    def test_api_error_with_retry_after_header(self) -> None:
        service = self._service()

        def response_for_attempt(attempt_count: int, request: Request) -> Response:
            if attempt_count == 1:
                return Response(
                    429,
                    headers={"Retry-After": "5", "content-type": "application/json"},
                    json={"errors": [{"message": "Rate limited"}]},
                    request=request,
                )
            return Response(200, json={}, request=request)

        dummy_client_class, _attempt_state = self._build_attempt_tracking_dummy_client(response_for_attempt)

        service.MAX_RETRY_ATTEMPTS = 2
        self._test_client_retry_behavior(service, dummy_client_class, 2)

    def test_network_timeout_handling(self) -> None:
        service = self._service()

        def response_for_attempt(attempt_count: int, request: Request) -> Response:
            if attempt_count == 1:
                return Response(504, json={"error": "Gateway timeout"}, request=request)
            return Response(200, json={}, request=request)

        dummy_client_class, _attempt_state = self._build_attempt_tracking_dummy_client(response_for_attempt)

        service.MAX_RETRY_ATTEMPTS = 1
        self._test_client_retry_behavior(service, dummy_client_class, 2)

    def test_graphql_error_handling(self) -> None:
        service = self._service()

        graphql_errors = {
            "errors": [
                {
                    "message": "Field 'invalidField' doesn't exist",
                    "extensions": {"code": "GRAPHQL_PARSE_FAILED", "category": "graphql"},
                }
            ]
        }

        dummy_client_class = build_dummy_http_client(
            send_callback=lambda _client, request: Response(
                200,  # GraphQL returns 200 even for errors
                json=graphql_errors,
                request=request,
                headers={"content-type": "application/json"},
            )
        )

        with self._client(service, dummy_client_class) as (client, fake_sleep):
            req = Request("POST", "http://t/graphql")
            client.send(req)

            self.assertEqual(len(client.send_calls), 1)
            fake_sleep.assert_not_called()

    def test_bulk_operation_throttling(self) -> None:
        service = self._service()
        service.MIN_API_POINTS = 30  # Set minimum points threshold

        request_count_state = self.RequestCountState()

        def send_response(_dummy_http_client: DummyHttpClient, request: Request) -> Response:
            request_count_state.request_count += 1
            if request_count_state.request_count == 1:
                available = 20
            else:
                available = 100
            return Response(
                200,
                json={"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": available, "restoreRate": 50}}}},
                request=request,
                headers={"content-type": "application/json"},
            )

        dummy_client_class = build_dummy_http_client(
            send_callback=send_response,
        )

        with self._client(service, dummy_client_class) as (client, fake_sleep):
            req = Request("POST", "http://t/bulk")
            client.send(req)

            self.assertTrue(fake_sleep.called)
            self.assertGreaterEqual(len(client.send_calls), 1)

    def test_api_version_mismatch_error(self) -> None:
        service = self._service()

        version_error = {
            "errors": [{"message": "API version 2024-10 is not supported", "extensions": {"code": "API_VERSION_NOT_SUPPORTED"}}]
        }

        dummy_client_class = build_dummy_http_client(
            send_callback=lambda _client, request: Response(
                400,
                json=version_error,
                request=request,
                headers={"content-type": "application/json"},
            )
        )

        with self._client(service, dummy_client_class) as (client, fake_sleep):
            req = Request("POST", "http://t/graphql")
            response = client.send(req)

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), version_error)

            self.assertEqual(len(client.send_calls), 1)
            fake_sleep.assert_not_called()

    def test_connection_reset_recovery(self) -> None:
        service = self._service()

        def response_for_attempt(attempt_count: int, request: Request) -> Response:
            if attempt_count <= 2:
                return Response(503, json={"error": "Service unavailable"}, request=request)
            return Response(200, json={}, request=request)

        dummy_client_class, _attempt_state = self._build_attempt_tracking_dummy_client(response_for_attempt)

        service.MAX_RETRY_ATTEMPTS = 3
        with self._client(service, dummy_client_class) as (client, fake_sleep):
            req = Request("GET", "http://t")
            result = client.send(req)

            self.assertEqual(result.status_code, 200)
            self.assertEqual(len(client.send_calls), 3)
            self.assertEqual(fake_sleep.call_count, 2)

    def test_invalid_credentials_no_retry(self) -> None:
        service = self._service()

        auth_error = {"errors": [{"message": "Invalid access token", "extensions": {"code": "UNAUTHORIZED"}}]}

        dummy_client_class = build_dummy_http_client(
            send_callback=lambda _client, request: Response(
                401,
                json=auth_error,
                request=request,
                headers={"content-type": "application/json"},
            )
        )

        service.MAX_RETRY_ATTEMPTS = 3
        with self._client(service, dummy_client_class) as (client, fake_sleep):
            req = Request("GET", "http://t")
            result = client.send(req)

            self.assertEqual(len(client.send_calls), 1)
            self.assertEqual(result.status_code, 401)
            fake_sleep.assert_not_called()

    def test_send_with_retry_delay_no_hard_throttle(self) -> None:
        service = self._service()

        def response_factory(request: Request) -> Response:
            return Response(
                200,
                json={"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 400, "restoreRate": 1}}}},
                request=request,
                headers={"content-type": "application/json"},
            )

        dummy_client_class: type[DummyHttpClient]
        send_func_state: TestShopifyService.SendFuncState
        dummy_client_class, send_func_state = self._build_send_func_dummy_client(response_factory)

        resp = Response(
            200,
            json={"extensions": {"cost": {"throttleStatus": {"currentlyAvailable": 400, "restoreRate": 1}}}},
            request=Request("GET", "http://t"),
            headers={"content-type": "application/json"},
        )

        responses = [resp, resp]

        def send_one(_request: Request) -> Response:
            return responses.pop(0)

        service.MAX_RETRY_ATTEMPTS = 1
        with (
            common.patch.object(_service_module, "Client", dummy_client_class),
            common.patch.object(_service_module, "sleep") as fake_sleep,
            common.patch.object(service, "_throttle_info", side_effect=[(False, 2), (False, None)]),
        ):
            client = service._create_http_client("t")
            dummy_client = self._assert_dummy_http_client(
                client,
                dummy_client_class,
                error_message="HTTP client was not constructed as DummyHttpClient",
            )
            send_func_state.send_function = send_one
            req = Request("GET", "http://t")
            result = dummy_client.send(req)
            self.assertEqual(result.status_code, 200)
            fake_sleep.assert_called_once_with(2)
            self.assertEqual(service.sync_record.hard_throttle_count, 0)

    def test_send_with_retry_invalid_json_transient(self) -> None:
        service = self._service()

        class InvalidJsonResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            request = Request("GET", "http://t")

            def json(self) -> dict:
                raise ValueError("bad")

            def close(self) -> None:
                pass

        dummy_client_class = build_dummy_http_client(
            init_callback=lambda dummy_http_client: setattr(dummy_http_client, "response", InvalidJsonResponse()),
        )

        service.MAX_RETRY_ATTEMPTS = 0
        with (
            common.patch.object(_service_module, "Client", dummy_client_class),
            common.patch.object(_service_module, "sleep") as fake_sleep,
            common.patch.object(_service_module, "THROTTLE_TRANSIENT_STATUS", {200}),
        ):
            client = service._create_http_client("t")
            req = Request("GET", "http://t")
            with self.assertRaises(ShopifyApiError):
                client.send(req)
            fake_sleep.assert_not_called()
