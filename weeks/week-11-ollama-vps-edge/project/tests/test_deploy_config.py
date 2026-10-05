"""Static checks on the VPS deploy files. They can't prove the VPS works (that needs a
real box -- see README), but they pin down the properties that make it safe."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NGINX = (ROOT / "deploy" / "ollama.nginx.conf").read_text()
SETUP = (ROOT / "scripts" / "setup_vps.sh").read_text()


def test_nginx_requires_basic_auth_on_the_proxy_location():
    proxy_block = NGINX.split("location / {")[1]
    assert "auth_basic" in proxy_block and "auth_basic_user_file" in proxy_block


def test_only_healthz_bypasses_auth():
    assert NGINX.count("auth_basic off") == 1
    healthz = NGINX.split("location = /healthz")[1].split("}")[0]
    assert "auth_basic off" in healthz


def test_nginx_proxies_to_loopback_ollama_and_streams():
    assert "proxy_pass http://127.0.0.1:11434;" in NGINX
    assert "proxy_buffering off;" in NGINX
    assert re.search(r"proxy_read_timeout\s+\d{3,}s", NGINX)  # generous for CPU inference


def test_nginx_never_listens_on_the_ollama_port():
    assert not re.search(r"listen\s+.*11434", NGINX)


def test_nginx_rate_limits():
    assert "limit_req_zone" in NGINX and "limit_req zone=" in NGINX


def test_setup_binds_ollama_to_loopback_and_never_opens_its_port():
    assert 'OLLAMA_HOST=127.0.0.1:11434' in SETUP
    assert not re.search(r"ufw allow\s+11434", SETUP)
    assert "ufw allow 443/tcp" in SETUP


def test_setup_gets_a_certificate_after_nginx_is_configured():
    assert SETUP.index("nginx -t") < SETUP.index("certbot --nginx")


def test_setup_does_not_hardcode_credentials():
    assert re.search(r'BASIC_AUTH_PASSWORD="\$\{BASIC_AUTH_PASSWORD:\?', SETUP)


@pytest.mark.parametrize("script", ["setup_vps.sh", "verify_endpoint.sh", "pull_model.sh"])
def test_scripts_are_valid_bash_and_strict(script):
    path = ROOT / "scripts" / script
    assert "set -euo pipefail" in path.read_text()
    subprocess.run(["bash", "-n", str(path)], check=True)


@pytest.mark.skipif(shutil.which("nginx") is None, reason="nginx not installed locally")
def test_nginx_conf_parses(tmp_path):
    conf = tmp_path / "nginx.conf"
    rendered = NGINX.replace("__SERVER_NAME__", "example.test").replace("__RATE__", "5").replace("__BURST__", "10")
    conf.write_text(
        f"events {{}}\nhttp {{\n{rendered}\n}}\n".replace(
            "/etc/nginx/.ollama_htpasswd", str(tmp_path / "htpasswd")
        )
    )
    (tmp_path / "htpasswd").write_text("u:{PLAIN}p\n")
    subprocess.run(["nginx", "-t", "-c", str(conf), "-p", str(tmp_path)], check=True)


def test_rate_limit_tokens_are_substituted_by_the_manual_setup_script_too():
    assert "__RATE__" in NGINX and "__BURST__" in NGINX
    assert "s/__RATE__/" in SETUP and "s/__BURST__/" in SETUP
