import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent
DOCKERFILE = (PROJECT_DIR / "Dockerfile").read_text()
DOCKERIGNORE = (PROJECT_DIR / ".dockerignore").read_text()


def test_is_multi_stage():
    assert DOCKERFILE.count("FROM ") >= 2


def test_runs_as_non_root_user():
    assert "USER appuser" in DOCKERFILE
    assert "useradd" in DOCKERFILE


def test_declares_a_healthcheck():
    assert "HEALTHCHECK" in DOCKERFILE


def test_listens_on_port_env_var_not_a_hardcoded_port():
    assert "$PORT" in DOCKERFILE
    assert "PORT=8080" in DOCKERFILE


def test_dockerignore_excludes_env_files_at_any_depth():
    # A bare `.env` entry only matches at the build context ROOT in Docker's ignore
    # syntax (unlike .gitignore, where it'd match any depth) -- this exact gap once
    # let a real, secret-bearing app/.env get copied straight into a pushed, deployed
    # image via `COPY app/ ./app/`. **/.env is the pattern that actually covers nested
    # paths; regression-tested here rather than trusted to eyeball review.
    assert "**/.env" in DOCKERIGNORE


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")
def test_no_env_file_ends_up_inside_a_built_image():
    (PROJECT_DIR / "app" / ".env").write_text("SHOULD_NOT_BE_IN_THE_IMAGE=true\n")
    try:
        subprocess.run(
            ["docker", "build", "--no-cache", "-q", "-t", "week09-dockerignore-test", str(PROJECT_DIR)],
            check=True, capture_output=True, text=True,
        )
        result = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "find", "week09-dockerignore-test", "/app", "-iname", "*.env*"],
            check=True, capture_output=True, text=True,
        )
        assert result.stdout.strip() == "", f"found .env file(s) inside the built image: {result.stdout}"
    finally:
        (PROJECT_DIR / "app" / ".env").unlink(missing_ok=True)
        subprocess.run(["docker", "rmi", "-f", "week09-dockerignore-test"], capture_output=True)
