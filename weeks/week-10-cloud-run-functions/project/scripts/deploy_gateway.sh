#!/usr/bin/env bash
# Wires API Gateway in front of northwind-rag-fn. Requires the function to already be
# deployed (its URL is rendered into gateway/openapi.yaml) and the
# apigw-rag-invoker service account to already have roles/run.invoker on it.
#
# `gcloud api-gateway apis create` and `api-configs create` are each slow (a few
# minutes) and are no-ops if already created/current, so this script is safe to re-run.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SA_EMAIL="apigw-rag-invoker@${PROJECT_ID}.iam.gserviceaccount.com"

FUNCTION_URL="$(gcloud run services describe northwind-rag-fn --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
SERVICE_URL="$(gcloud run services describe northwind-rag-svc --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"

RENDERED_SPEC="$(mktemp)"
FUNCTION_URL="$FUNCTION_URL" SERVICE_URL="$SERVICE_URL" envsubst '${FUNCTION_URL} ${SERVICE_URL}' < "$PROJECT_DIR/gateway/openapi.yaml" > "$RENDERED_SPEC"

gcloud api-gateway apis create northwind-rag-api --project="$PROJECT_ID" || true

CONFIG_ID="northwind-rag-config-$(date +%Y%m%d%H%M%S)"
gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api=northwind-rag-api \
  --openapi-spec="$RENDERED_SPEC" \
  --backend-auth-service-account="$SA_EMAIL" \
  --project="$PROJECT_ID"

gcloud api-gateway gateways create northwind-rag-gateway \
  --api=northwind-rag-api \
  --api-config="$CONFIG_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID" || \
gcloud api-gateway gateways update northwind-rag-gateway \
  --api=northwind-rag-api \
  --api-config="$CONFIG_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID"

rm -f "$RENDERED_SPEC"

echo
echo "Gateway hostname: $(gcloud api-gateway gateways describe northwind-rag-gateway --location="$REGION" --project="$PROJECT_ID" --format='value(defaultHostname)')"
