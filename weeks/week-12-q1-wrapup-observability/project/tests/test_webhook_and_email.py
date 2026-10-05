import json
import time

import pytest

from app import emailer, webhook

SECRET = "whsec_test"
EVENT = {
    "id": "evt-1",
    "type": "monitor-alert",
    "apiVersion": "v1",
    "payload": {
        "severity": "ALERT",
        "message": {"title": "Error rate above 2%", "body": "avg(request_error) is 0.05"},
        "window": "1h",
        "view": "scores-boolean",
        "fromTimestamp": "2026-10-04T10:00:00Z",
        "toTimestamp": "2026-10-04T11:00:00Z",
        "permalink": "https://cloud.langfuse.com/project/p/monitors/m",
        "filters": [{"column": "environment", "value": "cloud-run-service"}],
    },
}
BODY = json.dumps(EVENT).encode()


def header(ts, body=BODY, secret=SECRET):
    return f"t={ts},v1={webhook.sign(secret, str(ts), body)}"


# ---- signatures ---------------------------------------------------------------------------

def test_valid_signature_passes():
    now = int(time.time())
    webhook.verify(SECRET, header(now), BODY, now=now)


def test_matches_the_documented_algorithm():
    """HMAC-SHA256 over '<t>.<raw body>', hex digest -- re-derived independently of sign()."""
    import hashlib
    import hmac

    expected = hmac.new(SECRET.encode(), b"1700000000." + BODY, hashlib.sha256).hexdigest()
    assert webhook.sign(SECRET, "1700000000", BODY) == expected


@pytest.mark.parametrize(
    "mutate",
    [
        lambda ts: (header(ts, secret="other-secret"), BODY),   # wrong secret
        lambda ts: (header(ts), BODY + b" "),                    # body changed after signing
        lambda ts: (header(ts, body=b"{}"), BODY),               # signature for a different body
    ],
)
def test_tampering_is_rejected(mutate):
    now = int(time.time())
    hdr, body = mutate(now)
    with pytest.raises(webhook.InvalidSignature):
        webhook.verify(SECRET, hdr, body, now=now)


def test_replay_outside_tolerance_is_rejected():
    sent = 1_700_000_000
    with pytest.raises(webhook.InvalidSignature, match="replay"):
        webhook.verify(SECRET, header(sent), BODY, now=sent + 3600)


@pytest.mark.parametrize("hdr", [None, "", "garbage", "t=123", "v1=abc", "t=123,v1=nothex"])
def test_missing_or_malformed_header_is_rejected(hdr):
    with pytest.raises(webhook.InvalidSignature):
        webhook.verify(SECRET, hdr, BODY, now=123)


def test_no_configured_secret_rejects_everything():
    with pytest.raises(webhook.InvalidSignature, match="no webhook secret"):
        webhook.verify("", header(1), BODY, now=1)


def test_iso_and_millisecond_timestamps_are_understood():
    iso = "2026-10-04T11:00:00Z"
    epoch = webhook._to_epoch(iso)
    webhook.verify(SECRET, f"t={iso},v1={webhook.sign(SECRET, iso, BODY)}", BODY, now=epoch)
    assert webhook._to_epoch("1700000000000") == 1_700_000_000.0


# ---- routing + formatting -----------------------------------------------------------------

def test_which_events_get_emailed():
    assert webhook.should_notify(EVENT)
    assert webhook.should_notify({**EVENT, "payload": {**EVENT["payload"], "severity": "OK"}})  # recovery
    for severity in ("NO_DATA", "PAUSED", "UNKNOWN"):
        assert not webhook.should_notify({**EVENT, "payload": {**EVENT["payload"], "severity": severity}})
    assert not webhook.should_notify({**EVENT, "type": "something-else"})


def test_email_content_has_severity_window_and_link():
    subject, body = webhook.format_alert_email(EVENT)
    assert subject == "[Langfuse ALERT] Error rate above 2%"
    for fragment in ("avg(request_error) is 0.05", "ALERT", "1h", "cloud-run-service", "https://cloud.langfuse.com/project/p/monitors/m"):
        assert fragment in body


# ---- email --------------------------------------------------------------------------------

ENV = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_USERNAME": "me",
    "SMTP_PASSWORD": "pw",
    "ALERT_EMAIL_FROM": "alerts@example.com",
    "ALERT_EMAIL_TO": "a@example.com, b@example.com",
}


def test_config_reads_env_and_splits_recipients():
    cfg = emailer.EmailConfig.from_env(ENV)
    assert cfg.port == 587 and cfg.recipients == ("a@example.com", "b@example.com")


def test_missing_config_names_what_is_missing():
    with pytest.raises(RuntimeError, match="SMTP_HOST.*ALERT_EMAIL_TO"):
        emailer.EmailConfig.from_env({"ALERT_EMAIL_FROM": "x@y.z"})


def test_send_uses_starttls_then_login_then_send():
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, pw):
            calls.append(("login", user, pw))

        def send_message(self, msg):
            calls.append(("send", msg["Subject"], msg["To"]))

    emailer.send_email(emailer.EmailConfig.from_env(ENV), "subj", "body", smtp_factory=FakeSMTP)
    assert [c[0] for c in calls] == ["connect", "starttls", "login", "send"]  # TLS before credentials
    assert calls[-1] == ("send", "subj", "a@example.com, b@example.com")
