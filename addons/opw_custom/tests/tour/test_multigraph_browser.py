from ..common_imports import common
from ..fixtures.base import TourTestCase

from ..fixtures.multigraph_helpers import load_multigraph_action_context


@common.tagged(*common.TOUR_TAGS, "opw_custom")
class TestMultigraphBrowser(TourTestCase):
    def test_multigraph_view_no_errors(self) -> None:
        """Test that multigraph action exists and can be referenced"""
        load_multigraph_action_context(self, required_view_mode="multigraph")

        import logging

        _logger = logging.getLogger(__name__)
        _logger.info("✓ Multigraph action and model access test completed successfully")
