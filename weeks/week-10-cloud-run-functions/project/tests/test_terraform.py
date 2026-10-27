import shutil
import subprocess
from pathlib import Path

import pytest

TERRAFORM_DIR = Path(__file__).parent.parent / "terraform"


def test_function_uses_the_python313_runtime_and_is_min_instances_configurable():
    text = (TERRAFORM_DIR / "function.tf").read_text()
    assert 'runtime           = "python313"' in text
    assert "min_instance_count = var.function_min_instances" in text


def test_secret_iam_grant_has_no_hardcoded_secret_value():
    # Same regression test as Week 9's terraform/secrets.tf: the secret's own value
    # must only ever be created out-of-band via `gcloud secrets`, never via a
    # google_secret_manager_secret_version resource with a literal secret_data value
    # (which would put the real key into .tfstate).
    text = (TERRAFORM_DIR / "secrets.tf").read_text()
    assert "google_secret_manager_secret_iam_member" in text
    assert 'resource "google_secret_manager_secret_version"' not in text
    assert "secretAccessor" in text


def test_gateway_reuses_the_same_openapi_template_as_the_bash_script():
    text = (TERRAFORM_DIR / "gateway.tf").read_text()
    assert "gateway/openapi.yaml" in text
    assert "FUNCTION_URL" in text


def test_api_config_id_is_content_hashed_for_create_before_destroy():
    text = (TERRAFORM_DIR / "gateway.tf").read_text()
    assert "create_before_destroy = true" in text
    assert "md5(local.rendered_openapi_spec)" in text


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform CLI not installed")
def test_terraform_validate():
    subprocess.run(["terraform", "init", "-backend=false", "-input=false"], cwd=TERRAFORM_DIR, check=True, capture_output=True)
    result = subprocess.run(["terraform", "validate"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
