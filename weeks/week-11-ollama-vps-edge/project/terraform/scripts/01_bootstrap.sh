#!/usr/bin/env bash
# Step 1. Enables the APIs, creates the (empty) password secret, and puts a freshly
# generated password in it. Needs to run first because the VM reads that secret at
# boot -- if there were no version yet, the startup script would fail.
#
# Safe to re-run: an existing secret version is left alone (it never overwrites or
# prints your password). The plaintext is written only to .ollama_password (mode 600,
# gitignored) for the verify script and your .env -- never into Terraform state.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

terraform -chdir="$TERRAFORM_DIR" init -input=false
mapfile -t VARS < <(tf_vars)
terraform -chdir="$TERRAFORM_DIR" apply -input=false "${VARS[@]}" \
  -target=google_project_service.required \
  -target=google_secret_manager_secret.basic_auth

if gcloud secrets versions list "$BASIC_AUTH_SECRET_ID" --project="$PROJECT_ID" \
     --filter="state=ENABLED" --format="value(name)" --limit=1 | grep -q .; then
  echo "Secret $BASIC_AUTH_SECRET_ID already has a version -- leaving it alone."
  [[ -f "$PASSWORD_FILE" ]] || echo "(No local $PASSWORD_FILE: read it with gcloud secrets versions access latest --secret=$BASIC_AUTH_SECRET_ID)"
else
  umask 077
  openssl rand -base64 24 | tr -d '\n' > "$PASSWORD_FILE"
  gcloud secrets versions add "$BASIC_AUTH_SECRET_ID" --project="$PROJECT_ID" --data-file="$PASSWORD_FILE"
  echo "Generated a password -> $PASSWORD_FILE (mode 600)"
fi

echo
echo "Next: ./02_plan.sh"
