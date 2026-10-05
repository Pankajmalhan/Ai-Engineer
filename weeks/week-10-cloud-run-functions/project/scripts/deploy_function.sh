#!/usr/bin/env bash
# Deploys the RAG service as a Cloud Run function (2nd gen): source -> Google Cloud
# buildpacks -> container image in Artifact Registry -> Cloud Run, all in one command.
# Not run automatically by anything in this repo -- a human runs this on purpose.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
# ENABLE_LANGFUSE=1 sends traces to Langfuse: needs Secret Manager secrets langfuse-public-key and
# langfuse-secret-key (the runtime service account must be able to read them), and a Langfuse the
# deployed container can reach -- LANGFUSE_BASE_URL defaults to Langfuse Cloud.
SECRETS="OPENAI_API_KEY=openai-api-key:latest"
ENV_VARS="DEPLOY_TARGET=cloud-run-function,LANGFUSE_TRACING_ENVIRONMENT=cloud-run-function"
if [[ "${ENABLE_LANGFUSE:-0}" == "1" ]]; then
  SECRETS="$SECRETS,LANGFUSE_PUBLIC_KEY=langfuse-public-key:latest,LANGFUSE_SECRET_KEY=langfuse-secret-key:latest"
  ENV_VARS="$ENV_VARS,LANGFUSE_BASE_URL=${LANGFUSE_BASE_URL:-https://cloud.langfuse.com}"
fi
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

gcloud run deploy northwind-rag-fn \
  --source="$PROJECT_DIR/function" \
  --function=rag_chat \
  --base-image=python313 \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --min-instances="$MIN_INSTANCES" \
  --set-secrets="$SECRETS" \
  --set-env-vars="$ENV_VARS" \
  --quiet

echo
echo "Function URL: $(gcloud run services describe northwind-rag-fn --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
