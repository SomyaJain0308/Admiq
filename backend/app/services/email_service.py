import logging
import httpx

from backend.app.config import get_settings

logger = logging.getLogger("admiq.email")
settings = get_settings()

RESEND_API_URL = "https://api.resend.com/emails"


async def _send_email(to_email: str, subject: str, html: str, *, log_fallback: str) -> None:
    if not settings.resend_api_key:
        # No API key configured yet (e.g. local dev, or before RESEND_API_KEY
        # is set on Render) - fall back to logging so the flow can still be
        # built and tested end-to-end without a real provider.
        logger.info("RESEND_API_KEY not set - %s", log_fallback)
        return

    payload = {"from": settings.resend_from_email, "to": [to_email], "subject": subject, "html": html}
    headers = {"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(RESEND_API_URL, json=payload, headers=headers)
        if not response.is_success:
            # Don't raise - a failed email shouldn't 500 the calling endpoint
            # (which, for password reset, would also leak via response
            # timing/shape whether the email existed). Log it instead.
            logger.error("Resend returned %s sending to %s: %s", response.status_code, to_email, response.text)
    except httpx.RequestError as e:
        logger.error("Network error sending email to %s: %s", to_email, e)


async def send_password_reset_email(to_email: str, reset_link: str) -> None:
    html = (
        f"<p>We received a request to reset your Admiq staff password.</p>"
        f'<p><a href="{reset_link}">Click here to choose a new password</a>. '
        f"This link expires in 15 minutes.</p>"
        f"<p>If you didn't request this, you can safely ignore this email.</p>"
    )
    await _send_email(to_email, "Reset your Admiq password", html, log_fallback=f"password reset link for {to_email}: {reset_link}")


async def send_staff_invite_email(to_email: str, staff_name: str, college_name: str, invite_link: str) -> None:
    html = (
        f"<p>Hi {staff_name},</p>"
        f"<p>You've been added as staff for {college_name} on Admiq.</p>"
        f'<p><a href="{invite_link}">Click here to set your password</a> and get started. '
        f"This link expires in 48 hours.</p>"
    )
    await _send_email(to_email, f"You've been invited to Admiq - {college_name}", html, log_fallback=f"staff invite link for {to_email}: {invite_link}")
