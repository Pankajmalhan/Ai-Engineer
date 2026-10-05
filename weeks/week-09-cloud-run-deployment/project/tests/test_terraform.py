import shutil
import subprocess
from pathlib import Path

import pytest

TERRAFORM_DIR = Path(__file__).parent.parent / "terraform"


def test_scaling_min_max_instance_counts_are_present():
    text = (TERRAFORM_DIR / "cloud_run.tf").read_text()
    assert "min_instance_count" in text
    assert "max_instance_count" in text
    assert "scaling-cpu-target" in text


def test_cloud_armor_policy_has_a_rate_limit_rule():
    text = (TERRAFORM_DIR / "cloud_armor.tf").read_text()
    assert 'type        = "CLOUD_ARMOR"' in text
    assert "rate_limit_options" in text


def test_backend_service_is_wired_to_the_cloud_armor_policy():
    text = (TERRAFORM_DIR / "networking.tf").read_text()
    assert "security_policy" in text
    assert "SERVERLESS" in text


def test_secret_iam_grant_has_no_hardcoded_secret_value():
    # The secret's own value must only ever be created out-of-band via `gcloud
    # secrets` -- see secrets.tf's own comment for why. This is a regression test
    # against ever adding a google_secret_manager_secret_version with a literal
    # secret_data value to this file, which would put the real key into .tfstate.
    text = (TERRAFORM_DIR / "secrets.tf").read_text()
    assert "google_secret_manager_secret_iam_member" in text
    assert 'resource "google_secret_manager_secret_version"' not in text
    assert "secretAccessor" in text


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform CLI not installed")
def test_terraform_validate():
    subprocess.run(["terraform", "init", "-backend=false", "-input=false"], cwd=TERRAFORM_DIR, check=True, capture_output=True)
    result = subprocess.run(["terraform", "validate"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
