import ssl


def build_ssl_context(use_ssl: bool, verify_ssl: bool) -> ssl.SSLContext | None:
    if not use_ssl:
        return None

    secure_context = ssl.create_default_context()
    if not verify_ssl:
        secure_context.check_hostname = False
        secure_context.verify_mode = ssl.CERT_NONE
    return secure_context
