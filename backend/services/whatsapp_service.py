import requests

def send_whatsapp_text_message(phone_number_id: str, to: str, message: str, access_token: str) -> dict:
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

    response = requests.post(url, json=payload, headers=headers, timeout=10)

    return {
        "ok": response.ok,
        "status_code": response.status_code,
        "data": response.json() if response.content else None
    }
