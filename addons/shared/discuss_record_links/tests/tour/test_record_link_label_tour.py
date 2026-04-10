from ..common_imports import common
from ..fixtures.base import TourTestCase


@common.tagged(*common.TOUR_TAGS)
class TestRecordLinkLabelTour(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ensure_tour_product(default_code="1004", name="Widget E2E")
        cls.ensure_record_link_config(prefix="tproe2e")
        cls._drl_active_id = cls.ensure_discuss_channel_active_id()

    def test_record_link_label_tour(self) -> None:
        start_url = f"/odoo/action-mail.action_discuss?active_id={self._drl_active_id}"
        self.start_tour(start_url, "drl_record_link_label", login=self._get_test_login(), timeout=300)
