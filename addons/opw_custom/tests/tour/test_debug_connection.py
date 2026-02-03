"""Debug connection issues for tour tests"""

import logging
import socket
import subprocess
from odoo.tests import tagged
from ..base_types import TOUR_TAGS
from ..fixtures.base import TourTestCase

_logger = logging.getLogger(__name__)


@tagged(*TOUR_TAGS)
class TestDebugConnection(TourTestCase):
    """Debug connectivity between browser and Odoo server"""

    def test_server_is_listening(self) -> None:
        """Check if Odoo server is actually listening on the expected port"""
        port = self.http_port()
        _logger.info(f"Expected HTTP port: {port}")

        # Skip netstat check since it's not available in container
        # We'll use socket connectivity test which is more reliable anyway
        _logger.info("Using socket connectivity test (netstat not available in container)")

        # Try to connect to the port
        hosts_to_try = ["127.0.0.1", "localhost"]
        connection_successful = False

        for host in hosts_to_try:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    _logger.info(f"✓ Successfully connected to {host}:{port}")
                    connection_successful = True
                    break  # Found a working connection
                else:
                    _logger.warning(f"✗ Failed to connect to {host}:{port} (error code: {result})")
            except Exception as e:
                _logger.error(f"✗ Exception connecting to {host}:{port}: {e}")

        # Assert that at least one connection worked
        self.assertTrue(connection_successful, f"Could not connect to Odoo server on port {port}")

        # Check if we can curl the server
        for host in hosts_to_try:
            # noinspection HttpUrlsUsage
            url = f"http://{host}:{port}/web/webclient/version_info"
            try:
                result = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                    capture_output=True,
                    text=True,
                    timeout=8,  # fail fast; informational only
                )
                _logger.info(f"HTTP response from {url}: {result.stdout}")
            except subprocess.TimeoutExpired:
                _logger.warning(f"HTTP check timed out for {url}; proceeding (socket connectivity already verified)")

    def test_browser_url_format(self) -> None:
        """Check what URL format the browser is actually using"""
        # Get the base URL that would be used
        port = self.http_port()

        # Check environment variables
        import os

        _logger.info(f"Environment TEST_URL: {os.environ.get('TEST_URL', 'not set')}")
        _logger.info(f"Environment HOST: {os.environ.get('HOST', 'not set')}")

        # Try to get the URL from Odoo's test framework
        from odoo.tools import config

        _logger.info(f"Odoo config http_interface: {config.get('http_interface', 'not set')}")
        _logger.info(f"Odoo config http_port: {config.get('http_port', 'not set')}")

        # What URL would HttpCase construct?
        base_url = f"http://127.0.0.1:{port}"
        _logger.info(f"HttpCase would use base URL: {base_url}")

        self.assertTrue(port > 0, "Port should be valid")
