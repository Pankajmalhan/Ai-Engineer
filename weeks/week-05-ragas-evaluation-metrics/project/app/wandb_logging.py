"""Logs a RAGAS evaluation run to W&B as a baseline experiment. Runs offline by
default (writes to ./wandb/ locally, no account needed) -- same pattern as week 1b/1c
-- since this environment has no WANDB_API_KEY configured. `wandb login && wandb sync
wandb/offline-run-*` pushes a run to the cloud later.
"""

from __future__ import annotations

import os

from app.config import WANDB_MODE, WANDB_PROJECT

os.environ.setdefault("WANDB_MODE", WANDB_MODE)


def log_evaluation_run(scores: dict[str, float], sample_count: int, weakest_metric: str) -> None:
    import wandb

    run = wandb.init(project=WANDB_PROJECT, job_type="ragas-evaluation")
    run.log({**scores, "sample_count": sample_count})
    run.summary["weakest_metric"] = weakest_metric
    run.finish()
