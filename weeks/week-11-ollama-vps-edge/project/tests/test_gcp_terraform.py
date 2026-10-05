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
    assert "enable_secure_boot          = local.secure_boot" in text
    assert "enable_vtpm                 = true" in text
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


def _render_startup(tmp_path, expect_gpu: bool) -> str:
    (tmp_path / "main.tf").write_text(
        f'''
output "r" {{
  value = templatefile("{TF / "startup.sh.tftpl"}", {{
    server_name = "1-2-3-4.sslip.io", le_email = "a@b.co", ollama_model = "llama3.2:3b",
    expect_gpu = {str(expect_gpu).lower()}, num_parallel = 4, context_length = 4096,
    basic_auth_user = "rag", secret_id = "sec", project_id = "proj",
    nginx_conf = replace(replace(replace(file("{DEPLOY / "ollama.nginx.conf"}"), "__SERVER_NAME__", "1-2-3-4.sslip.io"), "__RATE__", "5"), "__BURST__", "10")
  }})
}}
'''
    )
    subprocess.run(["terraform", "apply", "-auto-approve", "-no-color"], cwd=tmp_path, check=True, capture_output=True)
    return subprocess.run(
        ["terraform", "output", "-raw", "r"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform CLI not installed")
@pytest.mark.parametrize("expect_gpu", [True, False])
def test_startup_template_renders_to_valid_bash(tmp_path, expect_gpu):
    rendered = _render_startup(tmp_path, expect_gpu)
    (tmp_path / "rendered.sh").write_text(rendered)
    subprocess.run(["bash", "-n", str(tmp_path / "rendered.sh")], check=True)

    assert "server_name 1-2-3-4.sslip.io;" in rendered  # nginx conf embedded + substituted
    assert "__SERVER_NAME__" not in rendered and "__RATE__" not in rendered and "__BURST__" not in rendered
    assert "rate=5r/s" in rendered and "burst=10 nodelay" in rendered
    assert '--secret="sec" --project="proj"' in rendered
    assert "OLLAMA_NUM_PARALLEL=4" in rendered and "OLLAMA_CONTEXT_LENGTH=4096" in rendered
    assert len(re.findall(r"^NGINX_CONF$", rendered, re.M)) == 1  # heredoc opens/closes once
    assert len(re.findall(r"^GPUCHECK$", rendered, re.M)) == 1
    assert "%{" not in rendered  # no unprocessed template directive leaked through

    # the on-VM diagnostic tool and its embedded python must be valid in both modes
    tool = re.search(r"<<'GPUCHECK'\n(.*?)\nGPUCHECK\n", rendered, re.S).group(1)
    (tmp_path / "gpucheck.sh").write_text(tool)
    subprocess.run(["bash", "-n", str(tmp_path / "gpucheck.sh")], check=True)
    for snippet in re.findall(r"<<'PY'\n(.*?)\nPY\n", tool, re.S):
        compile(snippet, "gpucheck-embedded", "exec")

    if expect_gpu:
        assert "cuda-drivers" in rendered and "OLLAMA_FLASH_ATTENTION=1" in rendered
        assert "GPU_VERIFIED" in rendered and "GPU_DRIVER_FAILED" in rendered
        assert rendered.index("cuda-drivers") < rendered.index("ollama.com/install.sh")  # driver first
    else:
        assert "cuda-drivers" not in rendered and "FLASH_ATTENTION" not in rendered


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


# ---- GPU deployment -------------------------------------------------------------------

def test_gpu_vm_scheduling_secure_boot_and_accelerator_wiring():
    text = _read("instance.tf")
    assert 'dynamic "guest_accelerator"' in text and "var.gpu_type" in text
    assert 'on_host_maintenance         = (local.has_gpu || var.use_spot) ? "TERMINATE" : "MIGRATE"' in text
    assert "!local.has_gpu" in text  # Secure Boot defaults off for GPU (unsigned NVIDIA module)
    assert 'regex("^(g2|a2|a3|g4)-", var.machine_type)' in text


def test_default_machine_is_a_gpu_machine_and_cpu_stays_available():
    variables = _read("variables.tf")
    assert 'default     = "g2-standard-4"' in variables
    assert "e2-medium" in variables  # documented CPU fallback


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform CLI not installed")
@pytest.mark.parametrize(
    "machine_type,gpu_type,has_gpu,parallel,secure_boot",
    [
        ("g2-standard-4", "", "true", "4", "false"),
        ("e2-medium", "", "false", "1", "true"),
        ("n1-standard-4", "", "false", "1", "true"),
        ("n1-standard-4", "nvidia-tesla-t4", "true", "4", "false"),
        ("a2-highgpu-1g", "", "true", "4", "false"),
    ],
)
def test_machine_type_drives_gpu_parallelism_and_secure_boot(machine_type, gpu_type, has_gpu, parallel, secure_boot):
    init = subprocess.run(["terraform", "init", "-backend=false", "-input=false"], cwd=TF, capture_output=True)
    if init.returncode != 0:
        pytest.skip("provider download unavailable (offline?)")
    out = subprocess.run(
        ["terraform", "console", "-no-color", "-var=project_id=p", "-var=le_email=a@b.co",
         f"-var=machine_type={machine_type}", f"-var=gpu_type={gpu_type}"],
        cwd=TF, input="[local.has_gpu, local.num_parallel, local.secure_boot]", capture_output=True, text=True, check=True,
    ).stdout
    assert re.findall(r"\b(true|false|\d+)\b", out) == [has_gpu, parallel, secure_boot]


def test_verify_script_fails_cpu_speed_and_cpu_placement_when_gpu_expected():
    import json
    import os

    text = (TF.parent / "scripts" / "verify_endpoint.sh").read_text()
    speed, placement = re.findall(r"python3 -c '\n(.*?)\n'", text, re.S)

    def run(snippet, payload, expect_gpu):
        return subprocess.run(
            ["python3", "-c", snippet], input=json.dumps(payload), text=True, capture_output=True,
            env={**os.environ, "EXPECT_GPU": expect_gpu, "MIN_TPS": "20"},
        )

    fast = {"prompt_eval_count": 30, "prompt_eval_duration": 3e8, "eval_count": 80, "eval_duration": 8e8}  # 100 tok/s
    cpu_speed = {**fast, "eval_duration": 1.8e10}  # 4.4 tok/s, what the e2-medium baseline measured
    assert run(speed, fast, "1").returncode == 0
    assert run(speed, cpu_speed, "1").returncode == 1
    assert run(speed, cpu_speed, "0").returncode == 0  # CPU deploys are not penalised

    on_gpu = {"models": [{"name": "m", "size": 3e9, "size_vram": 3e9}]}
    on_cpu = {"models": [{"name": "m", "size": 3e9, "size_vram": 0}]}
    split = {"models": [{"name": "m", "size": 3e9, "size_vram": 1.5e9}]}  # half spilled to CPU
    assert run(placement, on_gpu, "1").returncode == 0
    assert run(placement, on_cpu, "1").returncode == 1
    assert run(placement, split, "1").returncode == 1
    assert run(placement, on_cpu, "0").returncode == 0


def test_gpu_scripts_exist_and_quota_check_covers_zone_and_quota():
    assert (TF / "scripts" / "06_gpu_proof.sh").exists()
    quota = (TF / "scripts" / "00_check_gpu_quota.sh").read_text()
    assert "accelerator-types list" in quota and "NVIDIA_L4_GPUS" in quota


def test_quota_script_embedded_python_works_for_each_quota_situation():
    # Regression: the first version had doubled backslashes inside the embedded Python and
    # died with a SyntaxError the moment a user ran it. Run the real snippet on fake gcloud JSON.
    import json

    text = (TF / "scripts" / "00_check_gpu_quota.sh").read_text()
    code = re.search(r"python3 -c \'\n(.*?)\n\' \"\$GPU\"", text, re.S).group(1)

    def run(quotas):
        return subprocess.run(
            ["python3", "-c", code, "nvidia-l4"], input=json.dumps({"quotas": quotas}), text=True, capture_output=True
        )

    free = run([{"metric": "NVIDIA_L4_GPUS", "limit": 1, "usage": 0}])
    assert free.returncode == 0 and "OK: quota available" in free.stdout
    for quotas in (
        [{"metric": "NVIDIA_L4_GPUS", "limit": 0, "usage": 0}],  # new project default
        [{"metric": "NVIDIA_L4_GPUS", "limit": 1, "usage": 1}],  # all used
        [{"metric": "CPUS", "limit": 24, "usage": 0}],  # metric absent
    ):
        blocked = run(quotas)
        assert blocked.returncode == 1 and "Request an increase" in blocked.stdout
        assert "SyntaxError" not in blocked.stderr


def test_nginx_rate_limit_is_configurable_through_terraform():
    variables = _read("variables.tf")
    assert 'variable "nginx_rate_limit_per_second"' in variables and 'variable "nginx_rate_limit_burst"' in variables
    instance = _read("instance.tf")
    assert "var.nginx_rate_limit_per_second" in instance and "var.nginx_rate_limit_burst" in instance
