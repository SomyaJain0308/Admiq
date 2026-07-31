import httpx, hashlib, hmac
from datetime import datetime, timezone

from backend.schemas.models import InboundWhatsAppMessage



async def send_whatsapp_text_message(phone_number_id: str, to: str, message: str, access_token: str) -> dict:
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message
        }
    }

    headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload, headers=headers)

    return {
        "ok": response.is_success,
        "status_code": response.status_code,
        "data": response.json() if response.content else None
    }


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