import httpx, hashlib, hmac
from datetime import datetime, timedelta, timezone

from backend.app.monitoring.api_metrics import WHATSAPP_SEND_LATENCY_SECONDS, WHATSAPP_SEND_OUTCOMES
from backend.app.schemas.models import InboundWhatsAppMessage

# WhatsApp only allows free-form text within 24h of the user's last message
# to us; outside that a pre-approved template message is required instead.
WHATSAPP_SESSION_WINDOW_HOURS = 24


async def _send_whatsapp_payload(phone_number_id: str, payload: dict, access_token: str) -> dict:
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        with WHATSAPP_SEND_LATENCY_SECONDS.time():
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=payload, headers=headers)
    except httpx.RequestError as e:
        WHATSAPP_SEND_OUTCOMES.labels(outcome="network_error").inc()
        return {"ok": False, "status_code": None, "data": None, "error": str(e)}
    if response.status_code == 429:
        outcome = "rate_limited"
    elif response.is_success:
        outcome = "success"
    elif 400 <= response.status_code < 500:
        outcome = "client_error"
    elif response.status_code >= 500:
        outcome = "server_error"
    WHATSAPP_SEND_OUTCOMES.labels(outcome=outcome).inc()

    return {
        "ok": response.is_success,
        "status_code": response.status_code,
        "data": response.json() if response.content else None
    }


async def send_whatsapp_text_message(phone_number_id: str, to: str, message: str, access_token: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message
        }
    }
    return await _send_whatsapp_payload(phone_number_id, payload, access_token)


async def send_whatsapp_template_message(
    phone_number_id: str,
    to: str,
    access_token: str,
    template_name: str,
    language_code: str,
    body_params: list[str] | None = None,
) -> dict:
    template: dict = {"name": template_name, "language": {"code": language_code}}
    if body_params:
        # Assumes the approved template has exactly one body variable, which
        # gets filled with the staff member's message - matches how
        # send_staff_initiated_message below uses this.
        template["components"] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]}]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    }
    return await _send_whatsapp_payload(phone_number_id, payload, access_token)


async def send_staff_initiated_message(
    phone_number_id: str,
    to: str,
    message: str,
    access_token: str,
    last_inbound_message_at: datetime | None,
    template_name: str,
    template_language_code: str,
) -> dict:
    """
    Automated replies inside the webhook flow are always sent within the
    24-hour window (they're direct responses to an inbound message), but a
    staff-initiated send - a direct message, or a low-confidence-queue reply
    written hours or days after the question came in - is exactly the case
    where that window may have already closed. This checks last_inbound_
    message_at and picks whichever WhatsApp will actually accept, reporting
    which one via the "channel" key so a caller/UI can tell a normal reply
    apart from a templated fallback (which may read differently, since it's
    wrapped in the approved template's fixed wording rather than sent as
    plain text).

    last_inbound_message_at should be the student's own last message to us
    (e.g. StudentSession.last_message_at) - NOT the timestamp of our own
    last reply, which doesn't reopen or extend the window.
    """
    within_window = (
        last_inbound_message_at is not None
        and (datetime.utcnow() - last_inbound_message_at) < timedelta(hours=WHATSAPP_SESSION_WINDOW_HOURS)
    )

    if within_window:
        result = await send_whatsapp_text_message(phone_number_id=phone_number_id, to=to, message=message, access_token=access_token)
        result["channel"] = "text"
        return result

    result = await send_whatsapp_template_message(
        phone_number_id=phone_number_id,
        to=to,
        access_token=access_token,
        template_name=template_name,
        language_code=template_language_code,
        body_params=[message],
    )
    result["channel"] = "template"
    return result


def verify_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    received_signature = signature_header[len(prefix):]

    expected_signature = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256,).hexdigest()

    return hmac.compare_digest(received_signature, expected_signature)


def extract_whatsapp_message_events(payload) -> list[InboundWhatsAppMessage]:
    value = payload["entry"][0]["changes"][0]["value"]
    messages = value.get("messages", [])
    if not messages:
        return []

    if payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] != "text":
        return []

    event = InboundWhatsAppMessage(
    whatsapp_business_account_id = payload["entry"][0]["id"],
    phone_number_id = value["metadata"]["phone_number_id"],
    display_phone_number = value["metadata"]["display_phone_number"],
    
    whatsapp_user_id = value["contacts"][0]["wa_id"],
    student_name = value["contacts"][0]["profile"]["name"],
    student_phone = value["messages"][0]["from"],
    whatsapp_message_id = value["messages"][0]["id"],
    whatsapp_timestamp = datetime.fromtimestamp(int(value["messages"][0]["timestamp"]), tz=timezone.utc,),
    message_type = value["messages"][0]["type"],
    content = value["messages"][0]["text"]["body"],
    
    raw_payload = payload,
    )
    
    return [event]  