"""Run a bridge script inside another week's uv project and collect the trajectories it prints."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from agent_eval.trajectory import Trajectory, parse_jsonl_stream

ROOT = Path(__file__).resolve().parents[1]  # this project
WEEKS = ROOT.parents[1]  # .../weeks
W14_PROJECT = WEEKS / "week-14-supervisor-multi-agent-routing" / "project"
W16B_PROJECT = WEEKS / "week-16b-deep-agents-harness" / "project"


class BridgeError(RuntimeError):
    pass


def run_bridge(project: Path, script: str, args: list[str], timeout: int = 900) -> list[Trajectory]:
    uv = shutil.which("uv")
    if uv is None:
        raise BridgeError("uv is not on PATH")
    if not project.is_dir():
        raise BridgeError(f"project not found: {project}")
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}  # else uv warns about this project's venv
    proc = subprocess.run(
        [uv, "run", "--project", str(project), "python", str(ROOT / "bridges" / script), *args],
        cwd=project, env=env, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise BridgeError(f"{script} exited {proc.returncode}:\n{proc.stderr[-2000:]}")
    return list(parse_jsonl_stream(proc.stdout))
