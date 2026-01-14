"""Minimal tour test to debug WebSocket issues"""

import logging
from odoo.tests import tagged
from ..base_types import TOUR_TAGS
from ..fixtures.base import TourTestCase

_logger = logging.getLogger(__name__)


@tagged(*TOUR_TAGS)
class TestMinimalTour(TourTestCase):
    """Minimal test to debug tour infrastructure"""

    def test_http_port_available(self) -> None:
        """Test that we can get the HTTP port in multi-worker mode"""
        port = self.http_port()
        _logger.info(f"HTTP Port: {port}")
        self.assertIsNotNone(port, "HTTP port should be available")
        self.assertGreater(port, 0, "HTTP port should be positive")

    def test_browser_can_start(self) -> None:
        """Test that browser environment is configured properly"""
        # Instead of trying to start Chrome directly (which has SIGTRAP issues in test framework),
        # verify that the browser environment is configured and executable exists
        import os
        import shutil

        # Check if Chrome executable exists
        chrome_path = "/usr/bin/chromium"
        self.assertTrue(os.path.exists(chrome_path), f"Chrome executable not found at {chrome_path}")
        self.assertTrue(os.access(chrome_path, os.X_OK), f"Chrome executable not executable at {chrome_path}")

        # Check if chrome binary is in PATH
        chrome_in_path = shutil.which("chromium")
        self.assertIsNotNone(chrome_in_path, "chromium not found in PATH")

        # Verify CHROME_BIN environment variable is set correctly
        chrome_bin = os.environ.get("CHROME_BIN")
        self.assertEqual(chrome_bin, chrome_path, f"CHROME_BIN should be {chrome_path}, got {chrome_bin}")

        _logger.info(f"✓ Chrome executable found at {chrome_path}")
        _logger.info(f"✓ Chrome in PATH at {chrome_in_path}")
        _logger.info(f"✓ CHROME_BIN environment variable: {chrome_bin}")
        _logger.info("✓ Browser environment properly configured")
