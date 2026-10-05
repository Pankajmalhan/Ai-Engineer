#!/usr/bin/env bash
# Deletes every resource this week's scripts created. Run this once you're done
# reading the benchmark results -- min-instances=1 (or any >0) keeps billing for idle
# capacity for as long as the function/service stays up.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"

gcloud api-gateway gateways delete northwind-rag-gateway --location="$REGION" --project="$PROJECT_ID" --quiet || true
gcloud api-gateway apis delete northwind-rag-api --project="$PROJECT_ID" --quiet || true
gcloud run services delete northwind-rag-fn --region="$REGION" --project="$PROJECT_ID" --quiet || true
gcloud run services delete northwind-rag-svc --region="$REGION" --project="$PROJECT_ID" --quiet || true
gcloud iam service-accounts delete "apigw-rag-invoker@${PROJECT_ID}.iam.gserviceaccount.com" --project="$PROJECT_ID" --quiet || true
gcloud secrets delete openai-api-key --project="$PROJECT_ID" --quiet || true

echo "Torn down. Artifact Registry images in cloud-run-source-deploy are left in place -- delete that repo manually if you want those gone too."
