import base64

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request, Response, NotFound


class SingleDownloadController(http.Controller):
    @http.route("/odoo/binary/download_single", type="http", auth="user")
    def download_single(self, attachment_id: str, **_kwargs: str) -> Response | NotFound:
        attachment = request.env["ir.attachment"].browse(int(attachment_id))
        if not attachment.exists():
            return request.not_found()
        try:
            attachment.check_access("read")
        except AccessError:
            return request.not_found()

        file_content = base64.b64decode(attachment.datas)
        filename = attachment.name
        content_type = attachment.mimetype or "application/octet-stream"

        attachment.unlink()

        return Response(
            file_content,
            headers=[
                ("Content-Type", content_type),
                ("Content-Disposition", f'attachment; filename="{filename}"'),
                ("Content-Length", str(len(file_content))),
            ],
        )
