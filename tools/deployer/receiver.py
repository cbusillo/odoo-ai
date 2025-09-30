from __future__ import annotations

import argparse
import functools
import hmac
import json
import logging
import signal
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import DeploySettings, load_settings
from .queue import enqueue

LOGGER = logging.getLogger("deploy.receiver")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")


def deserialize_from_ref(ref_value: str) -> str:
    prefix = "refs/heads/"
    if ref_value.startswith(prefix):
        return ref_value.removeprefix(prefix)
    return ref_value


class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "DeployReceiver/1.0"
    settings: DeploySettings
    secret: bytes

    def do_POST(self) -> None:  # noqa: N802 - http.server signature
        header_signature = self.headers.get("X-Hub-Signature-256")
        event_type = self.headers.get("X-GitHub-Event", "")
        if event_type != "push":
            self._respond(HTTPStatus.ACCEPTED, {"status": "ignored", "reason": "unsupported event"})
            return

        if header_signature is None:
            self._respond(HTTPStatus.FORBIDDEN, {"status": "error", "reason": "missing signature"})
            return

        body_length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(body_length)
        if not self._verify_signature(header_signature, payload):
            self._respond(HTTPStatus.FORBIDDEN, {"status": "error", "reason": "signature mismatch"})
            return

        try:
            message = json.loads(payload)
        except json.JSONDecodeError as exc:
            LOGGER.warning("Invalid JSON payload: %s", exc)
            self._respond(HTTPStatus.BAD_REQUEST, {"status": "error", "reason": "invalid json"})
            return

        repository = message.get("repository", {}).get("name")
        ref_value = message.get("ref", "")
        branch = deserialize_from_ref(ref_value)
        if not repository or not branch:
            LOGGER.debug("Missing repository or branch in payload: %s", message)
            self._respond(HTTPStatus.ACCEPTED, {"status": "ignored", "reason": "incomplete payload"})
            return

        route = self.settings.find_route(repository, branch)
        if not route:
            LOGGER.info("No route configured for %s/%s", repository, branch)
            self._respond(HTTPStatus.ACCEPTED, {"status": "ignored", "reason": "no route"})
            return

        stack = self.settings.stack_for(route.stack)
        modules = self.settings.modules_for_route(route)

        task = {
            "repository": repository,
            "branch": branch,
            "stack": stack.name,
            "lane": route.lane,
            "modules": modules,
            "timestamp": datetime.now(UTC).isoformat(),
            "ref": ref_value,
            "before": message.get("before"),
            "after": message.get("after"),
            "compare": message.get("compare"),
            "head_commit": (message.get("head_commit") or {}).get("id"),
        }

        task_path = enqueue(stack.queue_dir, task)
        LOGGER.info("Enqueued %s -> %s", route.stack, task_path)

        if stack.wake_command:
            try:
                subprocess.run(stack.wake_command, check=True)
            except subprocess.CalledProcessError as exc:  # pragma: no cover - requires runtime environment
                LOGGER.warning("Wake command failed: %s", exc)

        self._respond(HTTPStatus.ACCEPTED, {"status": "queued", "stack": stack.name})

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: D401,N802 - quiet default logging
        LOGGER.debug(fmt, *args)

    def _verify_signature(self, header_signature: str, payload: bytes) -> bool:
        expected = hmac.new(self.secret, payload, sha256).hexdigest()
        prefix = "sha256="
        actual = header_signature.split("=", 1)[-1] if header_signature.startswith(prefix) else header_signature
        return hmac.compare_digest(expected, actual)

    def _respond(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_handler(settings: DeploySettings, secret: bytes) -> Callable[..., WebhookHandler]:
    class Handler(WebhookHandler):
        pass

    Handler.settings = settings  # type: ignore[assignment]
    Handler.secret = secret  # type: ignore[assignment]
    return Handler


def load_secret(secret_file: Path) -> bytes:
    secret = secret_file.read_bytes().strip()
    if not secret:
        msg = f"Secret file {secret_file} is empty"
        raise ValueError(msg)
    return secret


def run_server(settings: DeploySettings, host: str, port: int, secret: bytes) -> None:
    handler = build_handler(settings, secret)
    server = ThreadingHTTPServer((host, port), handler)
    LOGGER.info("Listening on %s:%s", host, port)

    def _shutdown(_signum: int, _frame: object) -> None:
        LOGGER.info("Shutting down receiver")
        server.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    server.serve_forever()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GitHub webhook receiver for Docker deploys")
    parser.add_argument("--config", type=Path, required=True, help="Path to deploy settings YAML file")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=9000, help="Bind port")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging(args.verbose)
    settings = load_settings(args.config)
    secret = load_secret(settings.webhook_secret_file)
    run_server(settings, args.host, args.port, secret)


if __name__ == "__main__":  # pragma: no cover
    main()
