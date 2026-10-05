#!/usr/bin/env bash
# Applies terraform/ with the image scripts/build_and_push.sh just pushed. This is the
# one command that actually changes what's running -- everything before it (build,
# push, validate) is safe to run repeatedly with no cloud-side effect.
#
# ENABLE_LANGFUSE=true sends traces to Langfuse (needs secrets langfuse-public-key and
# langfuse-secret-key in Secret Manager; LANGFUSE_BASE_URL overrides the Cloud URL).
#
# Not run automatically by anything in this repo: a human (or the CI job explicitly
# invoking it) runs this on purpose, after reviewing `terraform plan`.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$SERVICE_DIR/.last_image" ]]; then
  echo "No .last_image -- run scripts/build_and_push.sh first" >&2
  exit 1
fi
IMAGE="$(cat "$SERVICE_DIR/.last_image")"

cd "$SERVICE_DIR/terraform"
terraform init -input=false
terraform apply -input=false -auto-approve \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="image=${IMAGE}" \
  -var="enable_langfuse=${ENABLE_LANGFUSE:-false}" \
  -var="langfuse_base_url=${LANGFUSE_BASE_URL:-https://cloud.langfuse.com}"

echo
echo "Cloud Run URL (rejects direct traffic -- see ingress setting): $(terraform output -raw cloud_run_url)"
echo "Load balancer IP (this is the one to curl):                   $(terraform output -raw load_balancer_ip)"
