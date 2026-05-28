"""Email delivery — pluggable provider.

Dev default is "console" (logs the code, no signup needed). Set
EMAIL_PROVIDER=resend + RESEND_API_KEY in .env to send real emails via Resend.
"""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("olwen.email")


def _otp_html(code: str) -> str:
    return f"""
    <div style="font-family:system-ui,sans-serif;background:#02060A;color:#E2F5F1;padding:40px;border-radius:12px;max-width:420px;margin:auto">
      <p style="letter-spacing:4px;color:#5EEAD4;font-size:14px;margin:0 0 24px">{settings.app_name.upper()}</p>
      <p style="font-size:15px;color:#A7F3D0;margin:0 0 8px">Your verification code</p>
      <p style="font-size:38px;letter-spacing:10px;font-weight:300;color:#ECFEFF;margin:0 0 24px">{code}</p>
      <p style="font-size:12px;color:rgba(167,243,208,0.5);margin:0">
        This code expires in {settings.otp_expire_minutes} minutes. If you didn't request it, ignore this email.
      </p>
    </div>
    """


async def send_otp_email(to_email: str, code: str) -> None:
    """Send (or log) a verification code."""
    subject = f"Your {settings.app_name} verification code"

    if settings.email_provider == "resend" and settings.resend_api_key:
        await _send_via_resend(to_email, subject, _otp_html(code))
        logger.info("OTP emailed to %s via Resend", to_email)
    else:
        # Dev: print the code so you can test without an email service.
        print(f"\n  ✦ OLWEN OTP for {to_email}:  {code}\n", flush=True)
        logger.info("OTP for %s -> %s (console mode)", to_email, code)


async def _send_via_resend(to_email: str, subject: str, html: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
        )
        resp.raise_for_status()
