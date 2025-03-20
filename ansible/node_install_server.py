#!/usr/bin/env python3
import http.server
import logging
import mimetypes
import socketserver
import threading

from pathlib import Path
from typing import Callable

from tftpy import TftpServer

_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('tftpy').setLevel(logging.INFO)

FILES_TO_SERVE: dict[str, Path] = {
    "/id_rsa.pub": Path("~/.ssh/id_rsa.pub"),
    "/install.txt": Path("config/install.txt"),
    "/": Path("config/install.txt"),
    "/d-i/bookworm/preseed.cfg": Path("config/preseed.cfg"),
}

HTTP_HOST = "0.0.0.0"
HTTP_PORT = 80

TFTP_ROOT = Path("tftpboot")
TFTP_HOST = HTTP_HOST
TFTP_PORT = 69

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def return_file(self, file: Path) -> bool:
        if file.exists():
            content_type, _ = mimetypes.guess_type(file.name)
            content_type = content_type or 'application/octet-stream'
            file_bytes = file.read_bytes()

            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.send_header("Content-Length", str(len(file_bytes)))
            self.end_headers()
            self.wfile.write(file_bytes)
            _logger.debug(f"Served {file} ({content_type}) to {self.client_address}")
            return True
        else:
            _logger.error(f"File {file} not found")
            self.send_error(404)
            return False

    def do_GET(self) -> None:
        if self.path in FILES_TO_SERVE:
            self.return_file(FILES_TO_SERVE[self.path].expanduser())
            return
        local_path = TFTP_ROOT / self.path[1:]
        if Path(local_path).exists():
            self.return_file(local_path)
            return
        _logger.warning(f"File {self.path} not in scope")


if __name__ == '__main__':
    tftp_server = TftpServer(TFTP_ROOT)
    tftp_thread = threading.Thread(target=tftp_server.listen, args=(TFTP_HOST, TFTP_PORT), daemon=True)
    tftp_thread.start()
    _logger.info(f"TFTP server started on {TFTP_HOST}:{TFTP_PORT}, serving from {TFTP_ROOT}")

    handler_factory: Callable[..., CustomHandler] = CustomHandler
    with socketserver.TCPServer((HTTP_HOST, HTTP_PORT), handler_factory) as httpd:
        _logger.info(f"Serving HTTP on port {HTTP_PORT} (Ctrl+C to stop)...")
        httpd.serve_forever()