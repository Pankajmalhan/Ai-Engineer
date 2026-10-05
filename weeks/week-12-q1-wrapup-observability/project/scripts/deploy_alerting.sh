#!/usr/bin/env bash
# Deploys the two alerting functions from this project (main.py) and, optionally, the
# Cloud Scheduler job that drives the error-rate poller. Run on purpose, never by CI.
#
# Prerequisites (create once; values never go through this script's arguments or Terraform):
#   gcloud secrets create langfuse-public-key / langfuse-secret-key   (the Langfuse project's API keys)
#   gcloud secrets create langfuse-webhook-secret                     (the signing secret of the Langfuse webhook automation -- see its settings)
#   gcloud secrets create smtp-password
# and the runtime service account must be able to read them (roles/secretmanager.secretAccessor).
#
#   PROJECT_ID=... SMTP_HOST=smtp.gmail.com SMTP_USERNAME=you@gmail.com \
#   ALERT_EMAIL_FROM=you@gmail.com ALERT_EMAIL_TO=you@gmail.com ./scripts/deploy_alerting.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SMTP_HOST="${SMTP_HOST:?set SMTP_HOST}"
ALERT_EMAIL_FROM="${ALERT_EMAIL_FROM:?set ALERT_EMAIL_FROM}"
ALERT_EMAIL_TO="${ALERT_EMAIL_TO:?set ALERT_EMAIL_TO}"
SMTP_USERNAME="${SMTP_USERNAME:-}"
LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-https://cloud.langfuse.com}"
SCHEDULE="${SCHEDULE:-0 * * * *}"          # hourly; matches ERROR_RATE_WINDOW_MINUTES=60 so one breach = at most one e-mail/hour
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMMON_ENV="LANGFUSE_BASE_URL=${LANGFUSE_BASE_URL},SMTP_HOST=${SMTP_HOST},SMTP_USERNAME=${SMTP_USERNAME},ALERT_EMAIL_FROM=${ALERT_EMAIL_FROM},ALERT_EMAIL_TO=${ALERT_EMAIL_TO}"
COMMON_SECRETS="LANGFUSE_PUBLIC_KEY=langfuse-public-key:latest,LANGFUSE_SECRET_KEY=langfuse-secret-key:latest,SMTP_PASSWORD=smtp-password:latest"

echo "==> langfuse-webhook (public URL; protected by HMAC verification, not IAM)"
gcloud run deploy langfuse-alert-webhook \
  --source="$PROJECT_DIR" --function=langfuse_webhook --base-image=python313 \
  --region="$REGION" --project="$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars="$COMMON_ENV" \
  --set-secrets="$COMMON_SECRETS,LANGFUSE_WEBHOOK_SECRET=langfuse-webhook-secret:latest" \
  --quiet

echo "==> error-rate-check (private: only Cloud Scheduler may call it)"
gcloud run deploy error-rate-check \
  --source="$PROJECT_DIR" --function=error_rate_check --base-image=python313 \
  --region="$REGION" --project="$PROJECT_ID" \
  --no-allow-unauthenticated \
  --set-env-vars="$COMMON_ENV" \
  --set-secrets="$COMMON_SECRETS" \
  --quiet

CHECK_URL="$(gcloud run services describe error-rate-check --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
WEBHOOK_URL="$(gcloud run services describe langfuse-alert-webhook --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)')"

echo "==> Cloud Scheduler job (OIDC-authenticated call to the private function)"
SA="error-rate-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$SA" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud iam service-accounts create error-rate-scheduler --project="$PROJECT_ID" --display-name="Calls error-rate-check"
gcloud run services add-iam-policy-binding error-rate-check --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:$SA" --role="roles/run.invoker" >/dev/null
gcloud scheduler jobs create http error-rate-check --location="$REGION" --project="$PROJECT_ID" \
  --schedule="$SCHEDULE" --uri="$CHECK_URL" --http-method=POST \
  --oidc-service-account-email="$SA" --oidc-token-audience="$CHECK_URL" 2>/dev/null || \
gcloud scheduler jobs update http error-rate-check --location="$REGION" --project="$PROJECT_ID" \
  --schedule="$SCHEDULE" --uri="$CHECK_URL" --http-method=POST \
  --oidc-service-account-email="$SA" --oidc-token-audience="$CHECK_URL"

echo
echo "Langfuse webhook URL (paste into Langfuse > Automations > Webhook): $WEBHOOK_URL"
echo "Trigger the poller now:  gcloud scheduler jobs run error-rate-check --location=$REGION --project=$PROJECT_ID"
