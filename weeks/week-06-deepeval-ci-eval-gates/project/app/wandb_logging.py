"""Logs a DeepEval CI-gate run to W&B as a baseline experiment, same offline-by-default
pattern as Week 5. This is separate from the pytest gate itself -- pytest's job is
pass/fail; this is for tracking scores over time (e.g. to later move from fixed
thresholds to drop-from-baseline gating, per concept.md's tradeoffs section).
"""

from __future__ import annotations

import os

from app.config import WANDB_MODE, WANDB_PROJECT

os.environ.setdefault("WANDB_MODE", WANDB_MODE)


def log_eval_run(scores: dict[str, float], sample_count: int, break_retrieval: bool) -> None:
    import wandb

    run = wandb.init(project=WANDB_PROJECT, job_type="deepeval-ci-gate")
    run.log({**scores, "sample_count": sample_count})
    run.summary["break_retrieval"] = break_retrieval
    run.finish()
