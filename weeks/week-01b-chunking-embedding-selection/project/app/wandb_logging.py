"""Thin W&B wrapper: every chunking/embedding experiment run gets
chunking_strategy and embedding_model logged as run config, so results are
filterable/comparable in the W&B UI later, per this week's task.

Runs offline by default (writes to ./wandb/ locally) since this environment
has no WANDB_API_KEY configured -- `wandb sync` the run directories later to
push them to an online project once you're logged in. Set WANDB_MODE=online
(with WANDB_API_KEY set) to log live instead.
"""

import os

import wandb

PROJECT = "week-01b-chunking-embedding-selection"


def log_run(chunking_strategy: str, embedding_model: str, metrics: dict, part: str):
    mode = os.environ.get("WANDB_MODE", "offline")
    run = wandb.init(
        project=PROJECT,
        mode=mode,
        config={
            "chunking_strategy": chunking_strategy,
            "embedding_model": embedding_model,
            "part": part,
        },
        reinit=True,
    )
    run.log(metrics)
    run.finish()
