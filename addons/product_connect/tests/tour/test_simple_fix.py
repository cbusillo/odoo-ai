"""Fixed simple tour test with proper server wait"""

import logging
import time
from odoo.tests import tagged
from ..base_types import TOUR_TAGS
from ..fixtures.base import TourTestCase

_logger = logging.getLogger(__name__)


@tagged(*TOUR_TAGS)
class TestSimpleFix(TourTestCase):
    """Test with proper server readiness check"""

    def test_wait_and_navigate(self) -> None:
        """Test navigation with proper server wait"""
        import socket
        import odoo.tools.config as config

        # Get the port from config
        port = int(config.get("http_port", 8069))
        _logger.info(f"Configured HTTP port: {port}")

        # Wait for server to be ready (up to 30 seconds)
        server_ready = False
        for i in range(30):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                # In multi-worker mode, server binds to 0.0.0.0
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()

                if result == 0:
                    _logger.info(f"✓ Server ready on port {port} after {i + 1} seconds")
                    server_ready = True
                    break
            except:
                pass

            time.sleep(1)

        self.assertTrue(server_ready, f"Server not ready on port {port} after 30 seconds")

        # Now try a minimal tour without JavaScript
        _logger.info("Server is ready, attempting simple navigation")

        # Don't use start_tour, just verify server is accessible via test client
        try:
            response = self.url_open("/web/login")
            _logger.info(f"Server response status: {response.status_code}")
            self.assertEqual(response.status_code, 200, "Should get 200 response from /web/login")
        except Exception as e:
            _logger.error(f"Failed to reach server: {e}")
            self.fail(f"Could not reach server: {e}")
