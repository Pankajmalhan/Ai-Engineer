#!/usr/bin/env bash
# Deploys the RAG service as a Cloud Run function (2nd gen): source -> Google Cloud
# buildpacks -> container image in Artifact Registry -> Cloud Run, all in one command.
# Not run automatically by anything in this repo -- a human runs this on purpose.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

gcloud run deploy northwind-rag-fn \
  --source="$PROJECT_DIR/function" \
  --function=rag_chat \
  --base-image=python313 \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --min-instances="$MIN_INSTANCES" \
  --set-secrets=OPENAI_API_KEY=openai-api-key:latest \
  --quiet

echo
echo "Function URL: $(gcloud run services describe northwind-rag-fn --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
