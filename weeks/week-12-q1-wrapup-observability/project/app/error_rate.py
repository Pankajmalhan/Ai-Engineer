"""Error rate = share of requests that failed, computed from the `request_error` BOOLEAN
scores that app/tracing.py (identical in Weeks 9 and 10) writes: 1 per failed request, 0 per
successful one. Read through Langfuse's Public API (`api.scores.get_many`), paginated.

Why not an alert directly on Langfuse's side? A native alert evaluates ONE metric -- and a
boolean score's average (= the share that are true) is exactly an error rate, so the native
alert is the preferred production path (see README). This module is the other path: a poller
that owns the threshold logic and the e-mail, because Langfuse's alert channels are Slack,
Webhook and GitHub Actions -- not e-mail.

`min_requests` guards against alerting on noise: 1 failure in 8 requests is a "12.5% error
rate" and almost certainly nothing. Below the floor the result is reported as insufficient data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SCORE_NAME = "request_error"
DEFAULT_THRESHOLD = 0.02  # the roadmap's "error rate > 2%"
DEFAULT_MIN_REQUESTS = 20


@dataclass(frozen=True)
class ErrorRate:
    environment: str | None
    window_minutes: int
    total: int
    errors: int
    threshold: float = DEFAULT_THRESHOLD
    min_requests: int = DEFAULT_MIN_REQUESTS

    @property
    def rate(self) -> float:
        return self.errors / self.total if self.total else 0.0

    @property
    def enough_data(self) -> bool:
        return self.total >= self.min_requests

    @property
    def breached(self) -> bool:
        return self.enough_data and self.rate > self.threshold

    def describe(self) -> str:
        env = self.environment or "all environments"
        if not self.enough_data:
            return f"{env}: insufficient data ({self.total} requests in {self.window_minutes} min, need {self.min_requests})"
        state = "BREACHED" if self.breached else "ok"
        return (
            f"{env}: {self.rate:.1%} error rate ({self.errors}/{self.total} requests in "
            f"{self.window_minutes} min, threshold {self.threshold:.1%}) -> {state}"
        )


def fetch_error_rate(
    client,
    *,
    environment: str | None = None,
    window_minutes: int = 60,
    threshold: float = DEFAULT_THRESHOLD,
    min_requests: int = DEFAULT_MIN_REQUESTS,
    now: datetime | None = None,
    page_size: int = 100,
    max_pages: int = 500,
) -> ErrorRate:
    """`client` is a `langfuse.Langfuse` (anything with `.api.scores.get_many`)."""
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(minutes=window_minutes)

    total = errors = 0
    page = 1
    while page <= max_pages:
        response = client.api.scores.get_many(
            name=SCORE_NAME,
            environment=environment,
            from_timestamp=start,
            to_timestamp=end,
            limit=page_size,
            page=page,
        )
        for score in response.data:
            total += 1
            if float(score.value) >= 0.5:  # boolean scores arrive as 1.0 / 0.0
                errors += 1
        if page >= response.meta.total_pages:
            break
        page += 1

    return ErrorRate(
        environment=environment,
        window_minutes=window_minutes,
        total=total,
        errors=errors,
        threshold=threshold,
        min_requests=min_requests,
    )
