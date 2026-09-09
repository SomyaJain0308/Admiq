import httpx, hashlib, hmac, logging
from datetime import datetime, timedelta, timezone

from backend.app.monitoring.api_metrics import WHATSAPP_SEND_LATENCY_SECONDS, WHATSAPP_SEND_OUTCOMES
from backend.app.schemas.models import InboundWhatsAppMessage

logger = logging.getLogger(__name__)

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
    # Meta can (and regularly does) batch more than one message into a
    # single webhook delivery - e.g. a student sending two texts back to
    # back before the first delivery finishes, or multiple "changes" landing
    # together. This used to index straight to entry[0]/changes[0]/
    # messages[0], so anything past the very first message in the payload
    # was silently dropped - never saved, never answered, never logged.
    # Walking every entry -> every change -> every message instead means a
    # burst of messages actually all get processed.
    events: list[InboundWhatsAppMessage] = []

    for entry in payload.get("entry", []):
        whatsapp_business_account_id = entry.get("id")
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            if not messages:
                continue

            metadata = value.get("metadata", {})
            # Cloud API groups a batch of messages from the same
            # conversation under one "value", so there's normally exactly
            # one contact for however many messages are in it - contacts[0]
            # is the right one for every message in this value, not just
            # the first.
            contact = (value.get("contacts") or [{}])[0]

            for message in messages:
                message_type = message.get("type")
                if message_type != "text":
                    # Non-text messages (images, stickers, reactions, etc.)
                    # aren't handled yet - skip just this one message rather
                    # than the whole batch, and say so, instead of silently
                    # discarding it (and anything after it) like before.
                    logger.info(
                        "Skipping non-text WhatsApp message type=%s message_id=%s",
                        message_type,
                        message.get("id"),
                    )
                    continue

                text_body = message.get("text", {}).get("body")
                if text_body is None:
                    logger.warning("Skipping WhatsApp text message with no body message_id=%s", message.get("id"))
                    continue

                event = _build_event(payload, whatsapp_business_account_id, metadata, contact, message, message_type, text_body)
                if event is not None:
                    events.append(event)

    return events


def _build_event(payload, whatsapp_business_account_id, metadata, contact, message, message_type, text_body) -> InboundWhatsAppMessage | None:
    try:
        return InboundWhatsAppMessage(
            whatsapp_business_account_id=whatsapp_business_account_id,
            phone_number_id=metadata.get("phone_number_id"),
            display_phone_number=metadata.get("display_phone_number"),
            whatsapp_user_id=contact.get("wa_id"),
            student_name=contact.get("profile", {}).get("name"),
            student_phone=message.get("from"),
            whatsapp_message_id=message.get("id"),
            whatsapp_timestamp=datetime.fromtimestamp(int(message["timestamp"]), tz=timezone.utc),
            message_type=message_type,
            content=text_body,
            # Keep the whole webhook payload, not just this message - same
            # as before, just no longer implying (via a per-message copy)
            # that each event arrived in its own delivery.
            raw_payload=payload,
        )
    except Exception as e:
        # One malformed message record (missing field, bad timestamp, etc.)
        # shouldn't take down every other message in the same batch with
        # it - log and skip just this one.
        logger.error("Failed to parse WhatsApp message, skipping message_id=%s error=%s", message.get("id"), e, exc_info=True)
        return None