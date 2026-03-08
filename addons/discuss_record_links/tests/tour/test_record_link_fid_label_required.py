from ..common_imports import common
from ..fixtures.base import TourTestCase


@common.tagged(*common.TOUR_TAGS)
class TestRecordLinkFidLabelRequired(TourTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        product_record = cls.ensure_tour_product(default_code="1002", name="Widget FID")
        cls._drl_product_id = product_record.id
        cls.set_config_parameter(
            "drl_product_id_fid_required",
            cls._drl_product_id,
        )
        cls._drl_active_id = cls.ensure_discuss_channel_active_id()

    def test_record_link_fid_label_required(self) -> None:
        start_url = (
            f"/odoo/action-mail.action_discuss?active_id={self._drl_active_id}"
            f"&drl_disable=1&drl_product_id={self._drl_product_id}"
        )
        self.start_tour(
            start_url,
            "drl_record_link_fid_label_required",
            login=self._get_test_login(),
            timeout=300,
        )
