"""Provider-neutral authentication email delivery."""

from __future__ import annotations

import html
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from anyio import to_thread

from app.core.config import settings


class AuthEmailDeliveryError(RuntimeError):
    """Raised when an authentication email could not be accepted for delivery."""


class AuthEmailSender(Protocol):
    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None: ...


@dataclass(frozen=True, slots=True)
class RecordedOtpEmail:
    email: str
    code: str
    expires_minutes: int


class InMemoryAuthEmailSender:
    """Test/development sender that never writes OTPs to logs or responses."""

    def __init__(self) -> None:
        self.deliveries: list[RecordedOtpEmail] = []

    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None:
        self.deliveries.append(
            RecordedOtpEmail(email=email, code=code, expires_minutes=expires_minutes)
        )

    def latest_code_for(self, email: str) -> str:
        normalized = email.strip().casefold()
        for delivery in reversed(self.deliveries):
            if delivery.email.strip().casefold() == normalized:
                return delivery.code
        raise LookupError("No OTP delivery exists for this email")

    def clear(self) -> None:
        self.deliveries.clear()


class SmtpAuthEmailSender:
    """STARTTLS SMTP implementation used by Gmail during development."""

    async def send_otp(self, *, email: str, code: str, expires_minutes: int) -> None:
        try:
            await to_thread.run_sync(
                self._send_sync,
                email,
                code,
                expires_minutes,
            )
        except (OSError, smtplib.SMTPException, TimeoutError) as exc:
            raise AuthEmailDeliveryError(
                "We could not send the verification email. Please try again."
            ) from exc

    @staticmethod
    def _send_sync(email: str, code: str, expires_minutes: int) -> None:
        if (
            not settings.SMTP_HOST
            or not settings.SMTP_USERNAME
            or settings.SMTP_PASSWORD is None
            or not settings.SMTP_FROM_EMAIL
        ):
            raise AuthEmailDeliveryError("Authentication email delivery is not configured")

        sender_name = settings.SMTP_FROM_NAME.strip() or "Relay"
        message = EmailMessage()
        message["Subject"] = f"{code} is your Relay verification code"
        message["From"] = f"{sender_name} <{settings.SMTP_FROM_EMAIL}>"
        message["To"] = email
        message.set_content(
            "\n".join(
                [
                    "Relay verification code",
                    "",
                    code,
                    "",
                    f"This code expires in {expires_minutes} minutes and can be used once.",
                    "If you did not request this code, you can ignore this email.",
                ]
            )
        )
        safe_code = html.escape(code)
        html_body = (
            "<!doctype html><html lang=\"en\"><body "
            "style=\"margin:0;background:#f2f6f5;color:#12373a;"
            "font-family:Arial,sans-serif\"><div style=\"padding:32px 16px\">"
            "<div style=\"max-width:560px;margin:0 auto;background:#fff;"
            "border:1px solid #d9e6e3\"><div style=\"padding:24px 32px;"
            "border-bottom:1px solid #e5eeec;font-size:22px;font-weight:700\">"
            "Relay</div><div style=\"padding:32px\"><p style=\"margin:0 0 8px;"
            "color:#557174;font-size:13px;font-weight:700;text-transform:uppercase\">"
            "Secure sign in</p><h1 style=\"margin:0 0 16px;font-size:26px;"
            "line-height:1.25\">Verify your email</h1><p style=\"margin:0 0 24px;"
            "font-size:16px;line-height:1.6\">Enter this one-time code to continue "
            "to Relay.</p><div style=\"margin:0 0 24px;padding:18px;"
            "background:#edf7f4;border-left:4px solid #22a77a;"
            "font-family:Consolas,monospace;font-size:32px;font-weight:700;"
            f"letter-spacing:8px;text-align:center\">{safe_code}</div>"
            "<p style=\"margin:0;color:#557174;font-size:14px;line-height:1.6\">"
            f"The code expires in {expires_minutes} minutes and becomes invalid after "
            "one use. A newly requested code replaces the previous one.</p></div>"
            "<div style=\"padding:20px 32px;background:#143f43;color:#dcebea;"
            "font-size:12px;line-height:1.6\">If you did not request this email, "
            "no action is required.</div></div></div></body></html>"
        )
        message.add_alternative(
            html_body,
            subtype="html",
        )

        context = ssl.create_default_context()
        with smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        ) as client:
            client.ehlo()
            if settings.SMTP_STARTTLS:
                client.starttls(context=context)
                client.ehlo()
            client.login(
                settings.SMTP_USERNAME,
                settings.SMTP_PASSWORD.get_secret_value(),
            )
            client.send_message(message)


def configured_auth_email_sender() -> AuthEmailSender:
    if settings.AUTH_EMAIL_PROVIDER == "smtp":
        return SmtpAuthEmailSender()
    if not settings.is_local:
        raise RuntimeError("Authentication email delivery must use a configured provider")
    return InMemoryAuthEmailSender()


__all__ = [
    "AuthEmailDeliveryError",
    "AuthEmailSender",
    "InMemoryAuthEmailSender",
    "RecordedOtpEmail",
    "SmtpAuthEmailSender",
    "configured_auth_email_sender",
]
