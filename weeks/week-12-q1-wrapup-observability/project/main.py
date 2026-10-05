"""Two Cloud Run function entry points, deployed from this one source directory
(scripts/deploy_alerting.sh):

  langfuse_webhook   POST from a Langfuse alert automation. Public URL (Langfuse must reach it),
                     protected by HMAC verification -- NOT by IAM.
  error_rate_check   Called by Cloud Scheduler. Computes the error rate per deployment
                     environment from Langfuse and e-mails if it exceeds the threshold.
                     Private: only the scheduler's service account may invoke it.

Environment: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL (read access to the
project), LANGFUSE_WEBHOOK_SECRET, the SMTP_* / ALERT_EMAIL_* variables (app/emailer.py), and
optionally ERROR_RATE_THRESHOLD (0.02), ERROR_RATE_WINDOW_MINUTES (60), ERROR_RATE_MIN_REQUESTS
(20), ERROR_RATE_ENVIRONMENTS (comma list, default cloud-run-service,cloud-run-function).
"""

from __future__ import annotations

import json
import logging
import os

import functions_framework
from flask import Request, jsonify

from app import emailer, webhook
from app.error_rate import DEFAULT_MIN_REQUESTS, DEFAULT_THRESHOLD, fetch_error_rate

logger = logging.getLogger(__name__)


def _langfuse_client():
    from langfuse import Langfuse

    return Langfuse()  # LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL from env


@functions_framework.http
def langfuse_webhook(request: Request):
    raw_body = request.get_data()  # raw bytes: the signature covers exactly these
    try:
        webhook.verify(
            os.environ.get("LANGFUSE_WEBHOOK_SECRET", ""),
            request.headers.get(webhook.SIGNATURE_HEADER),
            raw_body,
            tolerance_seconds=int(os.environ.get("WEBHOOK_TOLERANCE_SECONDS", webhook.DEFAULT_TOLERANCE_SECONDS)),
        )
    except webhook.InvalidSignature as exc:
        logger.warning("rejected webhook: %s", exc)
        return jsonify(error="invalid signature"), 401

    try:
        event = json.loads(raw_body)
    except ValueError:
        return jsonify(error="body is not JSON"), 400

    if not webhook.should_notify(event):
        return jsonify(status="ignored", type=event.get("type")), 200

    subject, body = webhook.format_alert_email(event)
    emailer.send_email(emailer.EmailConfig.from_env(), subject, body)
    return jsonify(status="emailed", subject=subject), 200


@functions_framework.http
def error_rate_check(request: Request):
    threshold = float(os.environ.get("ERROR_RATE_THRESHOLD", DEFAULT_THRESHOLD))
    window = int(os.environ.get("ERROR_RATE_WINDOW_MINUTES", "60"))
    floor = int(os.environ.get("ERROR_RATE_MIN_REQUESTS", DEFAULT_MIN_REQUESTS))
    environments = [e.strip() for e in os.environ.get("ERROR_RATE_ENVIRONMENTS", "cloud-run-service,cloud-run-function").split(",") if e.strip()]

    client = _langfuse_client()
    results = [
        fetch_error_rate(client, environment=env, window_minutes=window, threshold=threshold, min_requests=floor)
        for env in environments
    ]
    breached = [r for r in results if r.breached]
    for r in results:
        logger.info(r.describe())

    if breached:
        subject = "[Langfuse ALERT] error rate above %.1f%% in %s" % (threshold * 100, ", ".join(r.environment for r in breached))
        body = "\n".join(r.describe() for r in results) + "\n"
        emailer.send_email(emailer.EmailConfig.from_env(), subject, body)

    return jsonify(
        breached=[r.environment for r in breached],
        results=[
            {"environment": r.environment, "total": r.total, "errors": r.errors, "rate": round(r.rate, 4), "breached": r.breached}
            for r in results
        ],
        emailed=bool(breached),
    )
