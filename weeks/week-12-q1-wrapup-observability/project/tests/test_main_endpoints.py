"""The deployed entry points, through functions-framework's own test client."""

import json
import time
from types import SimpleNamespace

import functions_framework
import pytest

import main
from app import webhook

SECRET = "whsec_test"
EVENT = {"type": "monitor-alert", "payload": {"severity": "ALERT", "message": {"title": "T", "body": "B"}, "window": "1h"}}


@pytest.fixture
def sent(monkeypatch):
    mails = []
    monkeypatch.setattr(main.emailer, "send_email", lambda cfg, subject, body, **kw: mails.append((subject, body)))
    monkeypatch.setattr(main.emailer.EmailConfig, "from_env", classmethod(lambda cls, env=None: object()))
    monkeypatch.setenv("LANGFUSE_WEBHOOK_SECRET", SECRET)
    return mails


# NOTE: functions_framework.create_app(source=main.__file__) loads main.py as a fresh module, so
# patching attributes of the `main` we imported would not reach the served code. We patch
# things the served module imports at call time instead (`langfuse.Langfuse`) or shares by
# identity (`app.emailer`).
def client(target):
    return functions_framework.create_app(target=target, source=main.__file__).test_client()


def signed(body: bytes, secret=SECRET, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    return {"x-langfuse-signature": f"t={ts},v1={webhook.sign(secret, ts, body)}", "Content-Type": "application/json"}


def test_webhook_emails_on_a_valid_alert(sent):
    body = json.dumps(EVENT).encode()
    response = client("langfuse_webhook").post("/", data=body, headers=signed(body))
    assert response.status_code == 200 and response.get_json()["status"] == "emailed"
    assert sent[0][0] == "[Langfuse ALERT] T"


def test_webhook_rejects_a_bad_signature_and_sends_nothing(sent):
    body = json.dumps(EVENT).encode()
    response = client("langfuse_webhook").post("/", data=body, headers=signed(body, secret="wrong"))
    assert response.status_code == 401 and sent == []


def test_webhook_rejects_unsigned_requests(sent):
    response = client("langfuse_webhook").post("/", data=b"{}", headers={"Content-Type": "application/json"})
    assert response.status_code == 401 and sent == []


def test_webhook_ignores_events_that_do_not_need_an_email(sent):
    body = json.dumps({**EVENT, "payload": {**EVENT["payload"], "severity": "NO_DATA"}}).encode()
    response = client("langfuse_webhook").post("/", data=body, headers=signed(body))
    assert response.status_code == 200 and response.get_json()["status"] == "ignored" and sent == []


def _fake_langfuse(per_env_scores):
    """per_env_scores: {environment: [0/1 values]}"""

    class Scores:
        def get_many(self, **kw):
            values = per_env_scores[kw["environment"]]
            return SimpleNamespace(
                data=[SimpleNamespace(value=float(v)) for v in values],
                meta=SimpleNamespace(total_pages=1),
            )

    return SimpleNamespace(api=SimpleNamespace(scores=Scores()))


def test_error_rate_check_emails_only_the_breached_environment(sent, monkeypatch):
    monkeypatch.setattr("langfuse.Langfuse", lambda: _fake_langfuse({
        "cloud-run-service": [0] * 100,                       # 0%
        "cloud-run-function": [1] * 10 + [0] * 90,            # 10%
    }))
    response = client("error_rate_check").post("/")
    body = response.get_json()
    assert body["breached"] == ["cloud-run-function"] and body["emailed"] is True
    assert len(sent) == 1 and "cloud-run-function" in sent[0][0] and "cloud-run-service" not in sent[0][0]


def test_error_rate_check_is_silent_when_healthy(sent, monkeypatch):
    monkeypatch.setattr("langfuse.Langfuse", lambda: _fake_langfuse({
        "cloud-run-service": [0] * 50, "cloud-run-function": [0] * 50,
    }))
    body = client("error_rate_check").post("/").get_json()
    assert body["breached"] == [] and body["emailed"] is False and sent == []


def test_error_rate_check_honours_threshold_from_env(sent, monkeypatch):
    monkeypatch.setenv("ERROR_RATE_THRESHOLD", "0.2")  # 10% is fine under a 20% threshold
    monkeypatch.setattr("langfuse.Langfuse", lambda: _fake_langfuse({
        "cloud-run-service": [1] * 10 + [0] * 90, "cloud-run-function": [0] * 50,
    }))
    assert client("error_rate_check").post("/").get_json()["breached"] == []
