#!/usr/bin/env bash
# Sourced by the other scripts -- not run directly. One place for the inputs every
# terraform command needs, so plan/apply/destroy always see identical -var values.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
LE_EMAIL="${LE_EMAIL:?set LE_EMAIL (email for certificate expiry notices)}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-us-central1-a}"
BASIC_AUTH_SECRET_ID="${BASIC_AUTH_SECRET_ID:-ollama-basic-auth-password}"
BASIC_AUTH_USER="${BASIC_AUTH_USER:-rag}"

TERRAFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASSWORD_FILE="$TERRAFORM_DIR/.ollama_password"

# Optional extras, passed straight through when set:
#   MACHINE_TYPE, OLLAMA_MODEL, DOMAIN_NAME, ALLOWED_SOURCE_RANGES (JSON list, e.g.
#   '["203.0.113.7/32"]'), ADMIN_MEMBERS (JSON list, e.g. '["user:you@example.com"]')
tf_vars() {
  local args=(
    -var="project_id=${PROJECT_ID}"
    -var="le_email=${LE_EMAIL}"
    -var="region=${REGION}"
    -var="zone=${ZONE}"
    -var="basic_auth_secret_id=${BASIC_AUTH_SECRET_ID}"
    -var="basic_auth_user=${BASIC_AUTH_USER}"
  )
  [[ -n "${MACHINE_TYPE:-}" ]] && args+=(-var="machine_type=${MACHINE_TYPE}")
  [[ -n "${OLLAMA_MODEL:-}" ]] && args+=(-var="ollama_model=${OLLAMA_MODEL}")
  [[ -n "${DOMAIN_NAME:-}" ]] && args+=(-var="domain_name=${DOMAIN_NAME}")
  [[ -n "${ALLOWED_SOURCE_RANGES:-}" ]] && args+=(-var="allowed_source_ranges=${ALLOWED_SOURCE_RANGES}")
  [[ -n "${ADMIN_MEMBERS:-}" ]] && args+=(-var="admin_members=${ADMIN_MEMBERS}")
  printf '%s\n' "${args[@]}"
}
