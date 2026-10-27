"""app/tracing.py against the REAL Langfuse SDK, exporting to a local capture server instead of
a Langfuse deployment. The fake-client tests prove our logic; this proves the SDK calls we make
(start_as_current_observation, propagate_attributes, create_score, flush) are real and valid and
put the right things on the wire -- including the environment that alerts filter on.
(Identical file in Week 10: the module under test is identical in both deployments.)
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCENARIO = Path(__file__).with_name("real_sdk_scenario.py")


def run(mode: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCENARIO), mode], capture_output=True, text=True, timeout=90, cwd=SCENARIO.parent.parent
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def ok():
    return run("ok")


@pytest.fixture(scope="module")
def failed():
    return run("fail")


def test_success_reaches_langfuse_flushed_with_environment_and_scores(ok):
    assert ok["answer"] == "30 days." and ok["raised"] is None
    # both the OTLP trace export AND the score ingestion were sent before the request returned
    assert "/api/public/otel/v1/traces" in ok["paths"] and "/api/public/ingestion" in ok["paths"]
    assert all(ok["wire_contains"][n] for n in ("rag-request", "retrieval", "generation", "cloud-run-function", "deploy_target"))
    assert ok["scores"]["request_error"] == {"value": 0.0, "dataType": "BOOLEAN", "environment": "cloud-run-function"}
    assert ok["scores"]["retrieval_hit_rate"]["value"] == 1.0


def test_failure_reaches_langfuse_as_an_error_and_is_still_raised(failed):
    assert failed["raised"] == "TimeoutError" and failed["answer"] is None
    assert failed["wire_contains"]["openai timed out"]  # the status message on the trace
    assert failed["scores"]["request_error"]["value"] == 1.0
    assert failed["scores"]["request_error"]["environment"] == "cloud-run-function"
    assert "retrieval_hit_rate" not in failed["scores"]
