"""Static and render checks for terraform/. They can't prove the deploy works on GCP
(that needs a project and credentials -- see README), but they pin down the security
properties that are easy to regress silently."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

TF = Path(__file__).resolve().parent.parent / "terraform"
DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def _read(name: str) -> str:
    """File text with full-line # comments removed, so assertions about what the config
    *does* aren't tripped by comments that merely mention a forbidden word."""
    lines = (TF / name).read_text().splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def _firewall_blocks() -> dict[str, str]:
    text = _read("network.tf")
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'resource "google_compute_firewall" "(\w+)" \{(.*?)\n\}', text, re.S)
    }


def test_exactly_the_expected_firewall_rules():
    assert set(_firewall_blocks()) == {"http", "https", "iap_ssh"}


def test_ssh_only_from_iap_range_never_the_internet():
    ssh = _firewall_blocks()["iap_ssh"]
    assert '"35.235.240.0/20"' in ssh
    assert "0.0.0.0/0" not in ssh


def test_no_rule_opens_the_ollama_port():
    for name, block in _firewall_blocks().items():
        assert "11434" not in block, name


def test_https_rule_uses_the_configurable_allowlist_and_http_stays_open_for_acme():
    blocks = _firewall_blocks()
    assert "source_ranges = var.allowed_source_ranges" in blocks["https"]
    assert '"0.0.0.0/0"' in blocks["http"]  # Let's Encrypt validators can't be range-limited


def test_vm_uses_a_dedicated_service_account_not_the_default():
    text = _read("instance.tf")
    assert "google_service_account.vm.email" in text
    assert "compute@developer.gserviceaccount.com" not in text
    assert "google_compute_default_service_account" not in _read("iam.tf")


def test_vm_hardening_flags():
    text = _read("instance.tf")
    assert 'enable-oslogin = "TRUE"' in text
    assert 'block-project-ssh-keys = "TRUE"' in text
    assert "enable_secure_boot          = true" in text
    assert not re.search(r"^\s*ssh-keys\s*=", text, re.M)  # no key files in metadata


def test_password_never_in_state_and_only_secret_accessor_is_granted():
    iam = _read("iam.tf")
    assert 'resource "google_secret_manager_secret_version"' not in iam
    assert "secret_data" not in iam
    assert "roles/secretmanager.secretAccessor" in iam
    # least privilege: no project-level role for the VM identity
    assert "google_project_iam_member" not in iam


def test_vm_reads_only_its_one_secret_at_secret_scope():
    iam = _read("iam.tf")
    block = re.search(r'resource "google_secret_manager_secret_iam_member" "vm_reads_password" \{(.*?)\n\}', iam, re.S)
    assert block and "google_secret_manager_secret.basic_auth.id" in block.group(1)


def test_static_ip_is_a_separate_resource_so_it_survives_vm_replacement():
    assert 'resource "google_compute_address" "ip"' in _read("network.tf")
    assert "nat_ip = google_compute_address.ip.address" in _read("instance.tf")


def test_tfvars_and_password_file_are_gitignored():
    ignore = (TF / ".gitignore").read_text()
    assert ".ollama_password" in ignore and "terraform.tfvars" in ignore and "terraform.tfstate*" in ignore


def test_startup_script_keeps_ollama_on_loopback_and_guards_tls_rewrite():
    text = _read("startup.sh.tftpl")
    assert "OLLAMA_HOST=127.0.0.1:11434" in text
    assert "gcloud secrets versions access latest" in text
    assert text.index("/etc/letsencrypt/live/") < text.index("certbot --nginx")  # only on first boot


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform CLI not installed")
def test_startup_template_renders_to_valid_bash(tmp_path):
    (tmp_path / "main.tf").write_text(
        f'''
output "r" {{
  value = templatefile("{TF / "startup.sh.tftpl"}", {{
    server_name = "1-2-3-4.sslip.io", le_email = "a@b.co", ollama_model = "llama3.2:3b",
    basic_auth_user = "rag", secret_id = "sec", project_id = "proj",
    nginx_conf = replace(file("{DEPLOY / "ollama.nginx.conf"}"), "__SERVER_NAME__", "1-2-3-4.sslip.io")
  }})
}}
'''
    )
    subprocess.run(["terraform", "apply", "-auto-approve", "-no-color"], cwd=tmp_path, check=True, capture_output=True)
    rendered = subprocess.run(
        ["terraform", "output", "-raw", "r"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
    (tmp_path / "rendered.sh").write_text(rendered)
    subprocess.run(["bash", "-n", str(tmp_path / "rendered.sh")], check=True)

    assert "server_name 1-2-3-4.sslip.io;" in rendered  # nginx conf embedded + substituted
    assert "__SERVER_NAME__" not in rendered
    assert '--secret="sec" --project="proj"' in rendered
    # the NGINX_CONF heredoc opens and closes exactly once
    assert len(re.findall(r"^NGINX_CONF$", rendered, re.M)) == 1


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform CLI not installed")
def test_terraform_fmt_and_validate():
    subprocess.run(["terraform", "fmt", "-check", "-recursive"], cwd=TF, check=True, capture_output=True)
    init = subprocess.run(["terraform", "init", "-backend=false", "-input=false"], cwd=TF, capture_output=True)
    if init.returncode != 0:
        pytest.skip("provider download unavailable (offline?)")
    subprocess.run(["terraform", "validate"], cwd=TF, check=True, capture_output=True)


@pytest.mark.parametrize("script", sorted(p.name for p in (TF / "scripts").glob("*.sh")))
def test_terraform_scripts_are_strict_bash(script):
    path = TF / "scripts" / script
    assert "set -euo pipefail" in path.read_text()
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_startup_script_sets_home_before_using_the_ollama_cli():
    # Regression: GCE's startup-script runner has no HOME and `ollama pull` panics
    # (exit 2) without it -- the first real deploy died exactly there.
    text = _read("startup.sh.tftpl")
    assert "export HOME=/root" in text
    assert text.index("export HOME=/root") < text.index("ollama pull")
