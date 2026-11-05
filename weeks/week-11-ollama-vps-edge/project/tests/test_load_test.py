import threading
import time
from types import SimpleNamespace

import pytest

from evals.load_test import LevelResult, format_table, percentile, run_level


def test_percentile_interpolates_and_handles_edges():
    assert percentile([], 50) == 0.0
    assert percentile([5.0], 95) == 5.0
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([1, 2, 3, 4, 5], 100) == 5
    assert percentile([0.0, 10.0], 95) == pytest.approx(9.5)


def test_run_level_actually_runs_requests_concurrently():
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def slow_answer(question):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return SimpleNamespace(output_tokens=10)

    result = run_level(slow_answer, ["q1", "q2"], concurrency=4, total_requests=12)

    assert peak == 4  # four workers overlapped
    assert result.ok == 12 and not result.errors
    assert result.output_tokens == 120
    # 12 requests x 0.05s serial would be 0.6s; with 4 workers it is ~0.15s
    assert result.wall_s < 0.45
    assert result.requests_per_second > 12 / 0.45


def test_concurrency_one_is_serial():
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def answer(question):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.01)
        with lock:
            in_flight -= 1
        return SimpleNamespace(output_tokens=1)

    run_level(answer, ["q"], concurrency=1, total_requests=5)
    assert peak == 1


def test_errors_are_recorded_not_raised_and_excluded_from_latency():
    def flaky(question):
        if question == "bad":
            raise RuntimeError("429 rate limited")
        return SimpleNamespace(output_tokens=5)

    result = run_level(flaky, ["good", "bad"], concurrency=2, total_requests=10)

    assert result.ok == 5 and len(result.errors) == 5
    assert all("RuntimeError: 429" in e for e in result.errors)
    assert len(result.latencies) == 5
    assert result.output_tokens == 25


def test_questions_are_cycled_so_every_request_gets_one():
    seen = []

    def answer(question):
        seen.append(question)
        return SimpleNamespace(output_tokens=0)

    run_level(answer, ["a", "b", "c"], concurrency=1, total_requests=7)
    assert seen == ["a", "b", "c", "a", "b", "c", "a"]


def test_throughput_properties_and_table():
    lv = LevelResult(concurrency=4, wall_s=2.0, latencies=[1.0, 1.0, 1.0, 3.0], output_tokens=80)
    assert lv.requests_per_second == 2.0 and lv.tokens_per_second == 40.0
    assert lv.p50 == 1.0 and lv.max_latency == 3.0
    table = format_table("ollama:llama3.2:3b", [lv])
    assert "ollama:llama3.2:3b" in table and "p95" in table and "40.0" in table
    assert LevelResult(concurrency=1).requests_per_second == 0.0  # no division by zero
