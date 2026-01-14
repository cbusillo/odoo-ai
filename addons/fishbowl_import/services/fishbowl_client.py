from __future__ import annotations

from dataclasses import dataclass
import ssl
from typing import Iterable, Iterator, Sequence

import pymysql


@dataclass(frozen=True)
class FishbowlConnectionSettings:
    host: str
    user: str
    password: str
    database: str
    port: int = 3306
    use_ssl: bool = True
    ssl_verify: bool = True


class FishbowlClient:
    def __init__(self, settings: FishbowlConnectionSettings) -> None:
        self._settings = settings
        self._connection: pymysql.connections.Connection | None = None

    def __enter__(self) -> "FishbowlClient":
        self._connection = self._open_connection()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # noqa: ANN001
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def fetch_all(self, query: str, params: Sequence[object] | None = None) -> list[dict[str, object]]:
        connection = self._require_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return list(rows)

    def stream_batches(
        self,
        query: str,
        params: Sequence[object] | None = None,
        *,
        batch_size: int = 1000,
    ) -> Iterator[list[dict[str, object]]]:
        connection = self._require_connection()
        cursor = connection.cursor(pymysql.cursors.SSDictCursor)
        try:
            cursor.execute(query, params)
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield list(rows)
        finally:
            cursor.close()

    def _open_connection(self) -> pymysql.connections.Connection:
        ssl_options: ssl.SSLContext | None = None
        if self._settings.use_ssl:
            ssl_options = ssl.create_default_context()
            if not self._settings.ssl_verify:
                ssl_options.check_hostname = False
                ssl_options.verify_mode = ssl.CERT_NONE
        return pymysql.connect(
            host=self._settings.host,
            user=self._settings.user,
            password=self._settings.password,
            database=self._settings.database,
            port=self._settings.port,
            charset="utf8mb4",
            autocommit=True,
            ssl=ssl_options,
        )

    def _require_connection(self) -> pymysql.connections.Connection:
        if self._connection is None:
            raise RuntimeError("Fishbowl connection is not initialized")
        return self._connection


def chunked(values: Iterable[object], batch_size: int) -> Iterator[list[object]]:
    batch: list[object] = []
    for value in values:
        batch.append(value)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
