"""Receives Langfuse alert webhooks and turns them into e-mail.

Langfuse alerts notify via Slack, Webhook or GitHub Actions (no e-mail), so the e-mail leg is
ours: Langfuse POSTs an HMAC-signed JSON body to an endpoint, this module verifies the
signature and formats the message.

Signature scheme, from Langfuse's webhook docs: header `x-langfuse-signature: t=<ts>,v1=<hex>`,
where v1 = HMAC-SHA256(secret, f"{ts}.{raw_body}"). The docs do not state a timestamp
tolerance; we enforce one anyway (default 5 minutes) so a captured webhook cannot be replayed
later. Verification uses the RAW body bytes -- re-serialising parsed JSON would change them.

Payload (type "monitor-alert"): payload.severity (UNKNOWN | OK | WARNING | ALERT | NO_DATA |
PAUSED), payload.message.{title,body}, payload.permalink, payload.window, payload.view,
payload.fromTimestamp / toTimestamp.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

SIGNATURE_HEADER = "x-langfuse-signature"
DEFAULT_TOLERANCE_SECONDS = 300
DEFAULT_NOTIFY_SEVERITIES = frozenset({"ALERT", "WARNING", "OK"})  # OK = the recovery e-mail


class InvalidSignature(Exception):
    pass


def parse_signature_header(header: str) -> tuple[str, str]:
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    if "t" not in parts or "v1" not in parts:
        raise InvalidSignature("malformed signature header")
    return parts["t"], parts["v1"]


def sign(secret: str, timestamp: str, raw_body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + raw_body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify(
    secret: str,
    header: str | None,
    raw_body: bytes,
    *,
    now: float | None = None,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> None:
    """Raises InvalidSignature unless the header proves `raw_body` was signed with `secret`
    recently. Returns None on success."""
    if not secret:
        raise InvalidSignature("no webhook secret configured")
    if not header:
        raise InvalidSignature("missing signature header")

    timestamp, received = parse_signature_header(header)
    try:
        bytes.fromhex(received)
        sent_at = _to_epoch(timestamp)
    except ValueError as exc:
        raise InvalidSignature("malformed signature header") from exc

    if not hmac.compare_digest(received, sign(secret, timestamp, raw_body)):
        raise InvalidSignature("signature mismatch")
    if abs((now if now is not None else time.time()) - sent_at) > tolerance_seconds:
        raise InvalidSignature("timestamp outside tolerance (possible replay)")


def _to_epoch(timestamp: str) -> float:
    """Accepts epoch seconds/milliseconds or an ISO-8601 string."""
    try:
        value = float(timestamp)
        return value / 1000.0 if value > 1e11 else value
    except ValueError:
        from datetime import datetime

        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()


def should_notify(event: dict, severities: frozenset[str] = DEFAULT_NOTIFY_SEVERITIES) -> bool:
    return (
        event.get("type") == "monitor-alert"
        and str(event.get("payload", {}).get("severity", "")).upper() in severities
    )


def format_alert_email(event: dict) -> tuple[str, str]:
    payload = event.get("payload", {})
    severity = str(payload.get("severity", "UNKNOWN")).upper()
    message = payload.get("message") or {}
    title = message.get("title") or "Langfuse alert"
    lines = [
        message.get("body") or "",
        "",
        f"Severity:  {severity}",
        f"Window:    {payload.get('window', '?')}  ({payload.get('fromTimestamp', '?')} -> {payload.get('toTimestamp', '?')})",
        f"Data view: {payload.get('view', '?')}",
    ]
    if payload.get("filters"):
        lines.append(f"Filters:   {json.dumps(payload['filters'])}")
    if payload.get("permalink"):
        lines += ["", f"Open in Langfuse: {payload['permalink']}"]
    return f"[Langfuse {severity}] {title}", "\n".join(lines).strip() + "\n"
