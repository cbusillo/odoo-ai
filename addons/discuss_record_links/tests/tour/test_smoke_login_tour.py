from ..common_imports import common
from ..fixtures.base import TourTestCase


@common.tagged(*common.TOUR_TAGS)
class TestDiscussRecordLinksSmokeTour(TourTestCase):
    def test_smoke_login_tour(self) -> None:
        self.start_tour("/web", "smoke_login_tour", login=self._get_test_login(), timeout=300)
