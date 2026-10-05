"""Weeks 9 and 10 each build their own container, so each carries its own copy of
app/tracing.py. They must be byte-identical: a fix applied to one and forgotten in the other
would give the two deployments different error/flush behaviour -- and different alerts."""

import re
from pathlib import Path

import pytest

WEEKS = Path(__file__).resolve().parents[3]
W9 = WEEKS / "week-09-cloud-run-deployment" / "project"
W10 = WEEKS / "week-10-cloud-run-functions" / "project"

pytestmark = pytest.mark.skipif(not (W9.exists() and W10.exists()), reason="week 9/10 projects not present")


def test_tracing_module_is_identical_in_both_deployments():
    assert (W9 / "app" / "tracing.py").read_text() == (W10 / "function" / "app" / "tracing.py").read_text()


def test_tracing_tests_are_identical_in_both_deployments():
    assert (W9 / "tests" / "test_tracing.py").read_text() == (W10 / "tests" / "test_tracing.py").read_text()


def test_real_sdk_tracing_tests_are_identical_in_both_deployments():
    for name in ("test_tracing_real_sdk.py", "real_sdk_scenario.py"):
        assert (W9 / "tests" / name).read_text() == (W10 / "tests" / name).read_text(), name


def test_the_function_entry_point_goes_through_tracing():
    main = (W10 / "function" / "main.py").read_text()
    assert "from app.tracing import traced_answer" in main and "traced_answer(_pipeline, question)" in main


def test_the_service_entry_point_goes_through_tracing():
    assert "traced_answer(_pipeline, request.question)" in (W9 / "app" / "main.py").read_text()


def test_the_function_ships_the_langfuse_dependency():
    assert re.search(r"^langfuse", (W10 / "function" / "requirements.txt").read_text(), re.M)


@pytest.mark.parametrize(
    "path,needle",
    [
        (W9 / "terraform" / "cloud_run.tf", 'DEPLOY_TARGET                = "cloud-run-service"'),
        (W10 / "terraform" / "observability.tf", 'DEPLOY_TARGET = "cloud-run-function"'),
        (W10 / "terraform" / "observability.tf", 'DEPLOY_TARGET = "cloud-run-service"'),
    ],
)
def test_each_target_sets_its_own_environment_name(path, needle):
    assert needle in path.read_text()


def test_langfuse_credentials_are_secrets_never_plain_env_in_either_stack():
    for tf in (W9 / "terraform" / "cloud_run.tf", W10 / "terraform" / "observability.tf"):
        text = tf.read_text()
        assert "langfuse-secret-key" in text
        # the secret key must only ever be wired through Secret Manager references
        assert not re.search(r"LANGFUSE_SECRET_KEY\s*=\s*\"(?!LANGFUSE)", text.replace('name = "LANGFUSE_SECRET_KEY"', ""))
