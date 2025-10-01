import time
import urllib.request


class HealthcheckError(RuntimeError):
    pass


def wait_for_health(url: str, timeout_seconds: int = 60, interval_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=interval_seconds) as response:
                status = response.getcode()
                if status == 200:
                    return
        except Exception as error:  # noqa: BLE001
            last_error = error
        time.sleep(interval_seconds)
    if last_error is not None:
        raise HealthcheckError(f"health check failed for {url}: {last_error}")
    raise HealthcheckError(f"health check failed for {url}")
