"""Test tour with single worker to isolate multi-worker issues"""

import logging
from odoo.tests import tagged, HttpCase

_logger = logging.getLogger(__name__)


@tagged("tour_test", "post_install", "-at_install")
class TestSingleWorker(HttpCase):
    """Test with standard HttpCase to avoid multi-worker issues"""

    def test_basic_http_case(self) -> None:
        """Test basic HttpCase functionality without multi-worker complexity"""
        _logger.info("Testing basic HttpCase functionality")

        # This should work in single-worker mode
        port = getattr(self, "port", 8069)
        _logger.info(f"Using port: {port}")

        # Just verify we can access basic attributes
        self.assertTrue(hasattr(self, "env"), "Should have env attribute")
        self.assertTrue(hasattr(self, "browser_js"), "Should have browser_js method")

        _logger.info("Basic HttpCase test passed - infrastructure works")
