"""Test server connectivity in multi-worker mode"""

import logging
import time
import socket
import subprocess
from odoo.tests import tagged
from ..base_types import TOUR_TAGS
from ..fixtures.base import TourTestCase

_logger = logging.getLogger(__name__)


@tagged(*TOUR_TAGS)
class TestWorkerConnectivity(TourTestCase):
    """Test if server is accessible in multi-worker mode"""

    def test_server_accessible_in_workers_mode(self) -> None:
        """Verify server is accessible when using --workers=2"""
        import odoo.service.server
        from odoo.tools import config

        # Log server configuration
        server = odoo.service.server.server
        _logger.info(f"Server type: {type(server).__name__}")
        _logger.info(f"Workers config: {config.get('workers', 0)}")

        # Get the expected port
        port = self.http_port()
        _logger.info(f"Expected port from http_port(): {port}")

        # Wait and test connectivity multiple times
        for attempt in range(10):
            time.sleep(1)

            # Try socket connection
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()

                if result == 0:
                    _logger.info(f"✓ Socket connected to 127.0.0.1:{port} on attempt {attempt + 1}")
                else:
                    _logger.warning(f"✗ Socket failed to connect on attempt {attempt + 1}")
            except Exception as e:
                _logger.error(f"Socket exception on attempt {attempt + 1}: {e}")

            # Try curl to the actual web endpoint
            try:
                result = subprocess.run(
                    [
                        "curl",
                        "-s",
                        "-o",
                        "/dev/null",
                        "-w",
                        "%{http_code}",
                        f"http://127.0.0.1:{port}/web/login",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                http_code = result.stdout.strip()
                if http_code == "200":
                    _logger.info(f"✓ HTTP 200 from /web/login on attempt {attempt + 1}")
                else:
                    _logger.warning(f"✗ HTTP {http_code} from /web/login on attempt {attempt + 1}")
            except Exception as e:
                _logger.error(f"Curl exception on attempt {attempt + 1}: {e}")

        # Check process status
        ps_result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        odoo_processes = [line for line in ps_result.stdout.split("\n") if "odoo-bin" in line]
        _logger.info(f"Found {len(odoo_processes)} odoo-bin processes")

        # Check listening ports (best-effort; skip if unavailable/permission denied)
        try:
            # noinspection SpellCheckingInspection
            netstat_result = subprocess.run(["netstat", "-tlnp"], capture_output=True, text=True)
            _logger.info(f"Listening on 8069: {':8069' in netstat_result.stdout}")
        except Exception as e:
            _logger.warning(f"Skipping netstat check due to error: {e}")
