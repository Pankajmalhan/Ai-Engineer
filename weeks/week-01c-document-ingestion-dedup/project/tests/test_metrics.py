import os

os.environ.setdefault("WANDB_MODE", "offline")

from app.metrics import log_ingestion_run


def test_log_ingestion_run_completes_offline_without_network():
    # WANDB_MODE=offline writes a local run under ./wandb/ -- no API key/login needed.
    log_ingestion_run(
        total_documents=100,
        duplicates_dropped=10,
        dedup_rate=0.10,
        pii_hits=5,
        documents_with_pii=4,
        pii_hit_rate=0.04,
        upserted=90,
        skipped=0,
        elapsed_seconds=1.23,
    )
