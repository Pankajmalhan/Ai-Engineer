#!/usr/bin/env bash
# Deploys the *same* app code as a plain Cloud Run service, via a hand-written
# Dockerfile (see function/Dockerfile) instead of buildpacks -- the comparison arm
# for "Cloud Run service vs Cloud Run function" (see concept.md). Building the
# buildpacks-produced function image directly as a service does NOT work (the CNB
# launcher needs wiring only the function-specific deploy path provides -- see
# concept.md's "Common pitfalls"), which is why this is a separate image/build.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
# ENABLE_LANGFUSE=1 sends traces to Langfuse: needs Secret Manager secrets langfuse-public-key and
# langfuse-secret-key (the runtime service account must be able to read them), and a Langfuse the
# deployed container can reach -- LANGFUSE_BASE_URL defaults to Langfuse Cloud.
SECRETS="OPENAI_API_KEY=openai-api-key:latest"
ENV_VARS="DEPLOY_TARGET=cloud-run-service,LANGFUSE_TRACING_ENVIRONMENT=cloud-run-service"
if [[ "${ENABLE_LANGFUSE:-0}" == "1" ]]; then
  SECRETS="$SECRETS,LANGFUSE_PUBLIC_KEY=langfuse-public-key:latest,LANGFUSE_SECRET_KEY=langfuse-secret-key:latest"
  ENV_VARS="$ENV_VARS,LANGFUSE_BASE_URL=${LANGFUSE_BASE_URL:-https://cloud.langfuse.com}"
fi
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/northwind-rag-svc:v1"

gcloud builds submit --tag="$IMAGE" --project="$PROJECT_ID" "$PROJECT_DIR/function"

gcloud run deploy northwind-rag-svc \
  --image="$IMAGE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --min-instances="$MIN_INSTANCES" \
  --set-secrets="$SECRETS" \
  --set-env-vars="$ENV_VARS" \
  --quiet

echo
echo "Service URL: $(gcloud run services describe northwind-rag-svc --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
