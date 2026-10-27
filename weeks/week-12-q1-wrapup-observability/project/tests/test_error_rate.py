import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.error_rate import ErrorRate, fetch_error_rate

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def score(value):
    return SimpleNamespace(value=float(value))


class FakeScores:
    """Serves `values` in pages like Langfuse does and records every call."""

    def __init__(self, values, page_size_hint=None):
        self.values = values
        self.calls = []

    def get_many(self, **kwargs):
        self.calls.append(kwargs)
        limit, page = kwargs["limit"], kwargs["page"]
        chunk = self.values[(page - 1) * limit : page * limit]
        total_pages = max(1, -(-len(self.values) // limit))
        return SimpleNamespace(
            data=[score(v) for v in chunk],
            meta=SimpleNamespace(page=page, limit=limit, total_items=len(self.values), total_pages=total_pages),
        )


def client_with(values):
    scores = FakeScores(values)
    return SimpleNamespace(api=SimpleNamespace(scores=scores)), scores


def test_rate_is_errors_over_requests_and_breaches_above_threshold():
    client, _ = client_with([1] * 3 + [0] * 97)  # 3%
    result = fetch_error_rate(client, environment="cloud-run-service", now=NOW)
    assert (result.total, result.errors) == (100, 3)
    assert result.rate == pytest.approx(0.03)
    assert result.breached


def test_exactly_at_threshold_is_not_a_breach():
    client, _ = client_with([1] * 2 + [0] * 98)  # exactly 2%
    assert not fetch_error_rate(client, now=NOW).breached


def test_healthy_traffic_is_ok():
    client, _ = client_with([0] * 200)
    result = fetch_error_rate(client, now=NOW)
    assert result.rate == 0 and not result.breached


def test_too_few_requests_never_alerts_even_at_100_percent_errors():
    client, _ = client_with([1] * 5)  # 100% of 5 requests
    result = fetch_error_rate(client, now=NOW)  # default floor is 20
    assert result.rate == 1.0 and not result.enough_data and not result.breached
    assert "insufficient data" in result.describe()


def test_no_traffic_at_all_is_not_an_error():
    client, _ = client_with([])
    result = fetch_error_rate(client, now=NOW)
    assert result.total == 0 and result.rate == 0.0 and not result.breached


def test_paginates_through_every_page():
    client, scores = client_with([1, 0] * 130)  # 260 scores, page size 100 -> 3 pages
    result = fetch_error_rate(client, now=NOW, page_size=100)
    assert result.total == 260 and result.errors == 130
    assert [c["page"] for c in scores.calls] == [1, 2, 3]


def test_query_is_scoped_by_name_environment_and_window():
    client, scores = client_with([0] * 30)
    fetch_error_rate(client, environment="cloud-run-function", window_minutes=30, now=NOW)
    call = scores.calls[0]
    assert call["name"] == "request_error"
    assert call["environment"] == "cloud-run-function"
    assert (call["to_timestamp"] - call["from_timestamp"]).total_seconds() == 30 * 60


def test_describe_mentions_threshold_and_state():
    text = ErrorRate("cloud-run-service", 60, total=100, errors=5).describe()
    assert "5.0%" in text and "BREACHED" in text and "2.0%" in text


def test_arguments_match_the_installed_sdk_signature():
    """Drift guard: if a Langfuse SDK upgrade renames these parameters, fail here, not in prod."""
    from langfuse import Langfuse

    api = Langfuse(public_key="pk", secret_key="sk", base_url="http://localhost:1").api
    inspect.signature(api.scores.get_many).bind(
        name="request_error", environment="x", from_timestamp=NOW, to_timestamp=NOW, limit=100, page=1
    )
    inspect.signature(api.trace.list).bind(environment="x", from_timestamp=NOW, limit=100)
