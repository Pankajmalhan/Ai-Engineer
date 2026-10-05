"""Plain SMTP e-mail (stdlib only). Works with any SMTP relay -- Gmail (app password), SendGrid's
SMTP endpoint, Mailgun, SES SMTP, a corporate relay. Configuration comes from the environment
(on Cloud Run: secrets for SMTP_PASSWORD, plain env for the rest):

    SMTP_HOST  SMTP_PORT (default 587, STARTTLS)  SMTP_USERNAME  SMTP_PASSWORD
    ALERT_EMAIL_FROM  ALERT_EMAIL_TO (comma-separated)
"""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    sender: str
    recipients: tuple[str, ...]

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "EmailConfig":
        env = os.environ if env is None else env
        missing = [k for k in ("SMTP_HOST", "ALERT_EMAIL_FROM", "ALERT_EMAIL_TO") if not env.get(k)]
        if missing:
            raise RuntimeError("missing e-mail configuration: " + ", ".join(missing))
        return cls(
            host=env["SMTP_HOST"],
            port=int(env.get("SMTP_PORT", "587")),
            username=env.get("SMTP_USERNAME") or None,
            password=env.get("SMTP_PASSWORD") or None,
            sender=env["ALERT_EMAIL_FROM"],
            recipients=tuple(a.strip() for a in env["ALERT_EMAIL_TO"].split(",") if a.strip()),
        )


def build_message(config: EmailConfig, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = config.sender
    msg["To"] = ", ".join(config.recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_email(config: EmailConfig, subject: str, body: str, smtp_factory=smtplib.SMTP) -> None:
    msg = build_message(config, subject, body)
    with smtp_factory(config.host, config.port, timeout=20) as smtp:
        smtp.starttls()
        if config.username:
            smtp.login(config.username, config.password or "")
        smtp.send_message(msg)
