from datetime import datetime

from ...services.repairshopr_sync_client import RepairshoprSyncClient, RepairshoprSyncConnectionSettings
from ..common_imports import common
from ..fixtures.base import UnitTestCase


@common.tagged(*common.UNIT_TAGS)
class TestRepairshoprSyncClient(UnitTestCase):
    def test_iter_batches_uses_resume_timestamp_and_id_ordering(self) -> None:
        client = RepairshoprSyncClient(
            RepairshoprSyncConnectionSettings(
                host="example",
                user="user",
                password="password",
                database="repairshopr",
                batch_size=2,
            )
        )

        captured_calls: list[tuple[str, list[object] | None]] = []
        responses = [
            [
                {"id": 11, "updated_at": datetime(2026, 1, 1, 12, 5, 0), "created_at": datetime(2026, 1, 1, 12, 0, 0)},
                {"id": 12, "updated_at": datetime(2026, 1, 1, 12, 5, 0), "created_at": datetime(2026, 1, 1, 12, 1, 0)},
            ],
            [],
        ]

        def fake_fetch_rows(query: str, parameters: list[object] | None = None) -> list[dict[str, object]]:
            captured_calls.append((query, list(parameters) if parameters is not None else None))
            return responses.pop(0)

        client._fetch_rows = fake_fetch_rows  # type: ignore[method-assign]

        batches = list(
            client._iter_batches(
                "repairshopr_data_ticket",
                ["id", "updated_at", "created_at"],
                updated_at="2022-01-01T00:00:00",
                updated_column="updated_at",
                created_column="created_at",
                after_id=10,
                resume_after_updated_at="2026-01-01T12:00:00",
            )
        )

        self.assertEqual(len(batches), 1)
        self.assertIn("ORDER BY GREATEST(updated_at, created_at), id", captured_calls[0][0])
        self.assertEqual(
            captured_calls[0][1],
            ["2026-01-01T12:00:00", "2026-01-01T12:00:00", 10, "2022-01-01T00:00:00", "2022-01-01T00:00:00", 2],
        )
        self.assertEqual(
            captured_calls[1][1],
            [datetime(2026, 1, 1, 12, 5, 0), datetime(2026, 1, 1, 12, 5, 0), 12, "2022-01-01T00:00:00", "2022-01-01T00:00:00", 2],
        )
