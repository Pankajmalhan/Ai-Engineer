import argparse
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import verify_traces as vt


def test_parse_target_validates_shape():
    assert vt.parse_target("cloud-run-service=https://1.2.3.4/chat") == ("cloud-run-service", "https://1.2.3.4/chat")
    for bad in ("nourl", "name=ftp://x", "=https://x", "name="):
        with pytest.raises(argparse.ArgumentTypeError):
            vt.parse_target(bad)


def test_send_requests_counts_only_2xx_and_survives_network_errors(capsys):
    codes = iter([200, 500, "boom", 204])

    def post(url, json):
        code = next(codes)
        if code == "boom":
            raise ConnectionError("refused")
        return SimpleNamespace(status_code=code)

    assert vt.send_requests(post, "http://x", 4) == 2
    assert "ConnectionError" in capsys.readouterr().err


class FakeLangfuse:
    """Traces/scores 'arrive' after `arrive_after` polls, like asynchronous ingestion."""

    def __init__(self, n, arrive_after=2):
        self.n, self.arrive_after, self.polls = n, arrive_after, 0
        outer = self

        class Trace:
            def list(self, **kw):
                outer.polls += 1
                shown = outer.n if outer.polls > outer.arrive_after else 0
                return SimpleNamespace(meta=SimpleNamespace(total_items=shown))

        class Scores:
            def get_many(self, **kw):
                shown = outer.n if outer.polls > outer.arrive_after else 0
                return SimpleNamespace(meta=SimpleNamespace(total_items=shown))

        self.api = SimpleNamespace(trace=Trace(), scores=Scores())


def fake_clock():
    t = {"now": 0.0}
    return (lambda: t["now"]), (lambda s: t.__setitem__("now", t["now"] + s))


def test_polls_until_traces_arrive():
    clock, sleep = fake_clock()
    lf = FakeLangfuse(5, arrive_after=2)
    traces, scores = vt.count_arrivals(
        lf, "cloud-run-function", datetime.now(timezone.utc), expected=5, timeout_s=60, poll_s=5, sleep=sleep, clock=clock
    )
    assert (traces, scores) == (5, 5) and lf.polls == 3


def test_gives_up_at_the_timeout_when_nothing_arrives():
    clock, sleep = fake_clock()
    lf = FakeLangfuse(5, arrive_after=10**6)
    traces, scores = vt.count_arrivals(
        lf, "x", datetime.now(timezone.utc), expected=5, timeout_s=20, poll_s=5, sleep=sleep, clock=clock
    )
    assert (traces, scores) == (0, 0) and clock() >= 20


def test_a_target_with_every_trace_passes_and_one_missing_traces_fails():
    clock, sleep = fake_clock()
    ok_post = lambda url, json: SimpleNamespace(status_code=200)

    good = vt.verify_target(FakeLangfuse(3, 0), ok_post, "cloud-run-service", "http://x", 3, timeout_s=10, poll_s=1, sleep=sleep, clock=clock)
    clock2, sleep2 = fake_clock()
    silent = vt.verify_target(FakeLangfuse(0, 0), ok_post, "cloud-run-function", "http://y", 3, timeout_s=10, poll_s=1, sleep=sleep2, clock=clock2)

    assert good.passed and not silent.passed
    table = vt.format_results([good, silent])
    assert "PASS" in table and "FAIL" in table


def test_failed_http_requests_fail_the_target_even_if_old_traces_exist():
    clock, sleep = fake_clock()
    down = lambda url, json: SimpleNamespace(status_code=503)
    result = vt.verify_target(FakeLangfuse(0, 0), down, "cloud-run-service", "http://x", 3, timeout_s=5, poll_s=1, sleep=sleep, clock=clock)
    assert result.http_ok == 0 and not result.passed
