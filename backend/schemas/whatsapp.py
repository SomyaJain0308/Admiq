from pydantic import BaseModel
from datetime import datetime


class InboundWhatsAppMessage(BaseModel):
    whatsapp_business_account_id: str
    phone_number_id: str
    display_phone_number: str
    whatsapp_user_id: str
    student_name: str | None = None
    student_phone: str
    whatsapp_message_id: str
    whatsapp_timestamp: datetime
    message_type: str
    content: str
    raw_payload: dict