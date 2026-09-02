import os

# --- Vector store --------------------------------------------------------------------
# Postgres + pgvector, started via `docker compose up -d` (see docker-compose.yml).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://week1c:week1c@localhost:5434/week1c_ingestion"
)

# --- MinHash near-duplicate detection -------------------------------------------------
# datasketch's MinHashLSH approximates Jaccard similarity; NUM_PERM trades accuracy
# (higher = closer to true Jaccard) for memory/CPU per document.
MINHASH_NUM_PERM = int(os.environ.get("MINHASH_NUM_PERM", "256"))
MINHASH_SHINGLE_SIZE = int(os.environ.get("MINHASH_SHINGLE_SIZE", "3"))  # word n-gram size
DEDUP_JACCARD_THRESHOLD = float(os.environ.get("DEDUP_JACCARD_THRESHOLD", "0.85"))

# --- PII redaction ---------------------------------------------------------------------
# Presidio's default NLP engine; requires `python -m spacy download en_core_web_sm`.
# Unset/undownloaded -> PresidioPIIRedactor.is_available() is False and callers should
# fall back to RegexPIIRedactor (regex-only, catches EMAIL/PHONE/ID but no NER entities
# like PERSON/LOCATION).
PII_SPACY_MODEL = os.environ.get("PII_SPACY_MODEL", "en_core_web_sm")
PII_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "ID_NUMBER", "PERSON"]

# --- W&B metrics -----------------------------------------------------------------------
# Defaults to local offline mode -- no WANDB_API_KEY/login required to log runs; set
# WANDB_MODE=online (and log in) to actually sync to a W&B project.
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "week1c-document-ingestion")
WANDB_MODE = os.environ.get("WANDB_MODE", "offline")
