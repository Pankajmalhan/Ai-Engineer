#!/usr/bin/env bash
# Sourced by every other script in this directory -- not run directly. Centralizes
# the variables every terraform command needs, so PROJECT_ID/REGION/etc. are only
# ever set in one place, matching ../../scripts/*.sh's own convention.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPO_ID="${REPO_ID:-northwind-rag-tf}"

TERRAFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTION_DIR="$TERRAFORM_DIR/../function"
LAST_IMAGE_FILE="$TERRAFORM_DIR/.last_image"

# Every script below passes exactly these -var flags, so plan/apply/destroy always
# see the same inputs -- the single most common source of "terraform wants to
# destroy and recreate everything" surprises is a plan run with different -var
# values than the last apply.
tf_vars() {
  local args=(-var="project_id=${PROJECT_ID}" -var="region=${REGION}" -var="artifact_repo_id=${REPO_ID}")
  if [[ -f "$LAST_IMAGE_FILE" ]]; then
    args+=(-var="service_image=$(cat "$LAST_IMAGE_FILE")")
  fi
  printf '%s\n' "${args[@]}"
}
