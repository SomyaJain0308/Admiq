import hashlib
import hmac


def verify_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    received_signature = signature_header[len(prefix):]

    expected_signature = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256,).hexdigest()

    return hmac.compare_digest(received_signature, expected_signature)