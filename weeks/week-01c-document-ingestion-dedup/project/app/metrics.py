"""W&B logging for data-quality metrics -- dedup rate and PII hit rate tell you how
messy each ingestion batch was, tracked over time instead of only checked once.
Defaults to WANDB_MODE=offline (writes a local run under ./wandb/, no login/API key
required); set WANDB_MODE=online to actually sync to a project.
"""

from __future__ import annotations

import os

from app.config import WANDB_MODE, WANDB_PROJECT


def log_ingestion_run(
    *,
    total_documents: int,
    duplicates_dropped: int,
    dedup_rate: float,
    pii_hits: int,
    documents_with_pii: int,
    pii_hit_rate: float,
    upserted: int,
    skipped: int,
    elapsed_seconds: float,
) -> None:
    os.environ.setdefault("WANDB_MODE", WANDB_MODE)
    import wandb

    run = wandb.init(project=WANDB_PROJECT, job_type="ingestion")
    run.log(
        {
            "total_documents": total_documents,
            "duplicates_dropped": duplicates_dropped,
            "dedup_rate": dedup_rate,
            "pii_hits": pii_hits,
            "documents_with_pii": documents_with_pii,
            "pii_hit_rate": pii_hit_rate,
            "upserted": upserted,
            "skipped": skipped,
            "elapsed_seconds": elapsed_seconds,
        }
    )
    run.finish()
