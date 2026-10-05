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
#   MACHINE_TYPE (default g2-standard-4 = 1x L4 GPU; e2-medium for CPU-only), GPU_TYPE, GPU_COUNT,
#   USE_SPOT (true|false), NGINX_RATE_LIMIT_PER_SECOND, NGINX_RATE_LIMIT_BURST, BOOT_DISK_GB, OLLAMA_NUM_PARALLEL, OLLAMA_MODEL, DOMAIN_NAME, ALLOWED_SOURCE_RANGES (JSON list, e.g.
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
  [[ -n "${GPU_TYPE:-}" ]] && args+=(-var="gpu_type=${GPU_TYPE}")
  [[ -n "${GPU_COUNT:-}" ]] && args+=(-var="gpu_count=${GPU_COUNT}")
  [[ -n "${USE_SPOT:-}" ]] && args+=(-var="use_spot=${USE_SPOT}")
  [[ -n "${BOOT_DISK_GB:-}" ]] && args+=(-var="boot_disk_gb=${BOOT_DISK_GB}")
  [[ -n "${OLLAMA_NUM_PARALLEL:-}" ]] && args+=(-var="ollama_num_parallel=${OLLAMA_NUM_PARALLEL}")
  [[ -n "${NGINX_RATE_LIMIT_PER_SECOND:-}" ]] && args+=(-var="nginx_rate_limit_per_second=${NGINX_RATE_LIMIT_PER_SECOND}")
  [[ -n "${NGINX_RATE_LIMIT_BURST:-}" ]] && args+=(-var="nginx_rate_limit_burst=${NGINX_RATE_LIMIT_BURST}")
  [[ -n "${OLLAMA_MODEL:-}" ]] && args+=(-var="ollama_model=${OLLAMA_MODEL}")
  [[ -n "${DOMAIN_NAME:-}" ]] && args+=(-var="domain_name=${DOMAIN_NAME}")
  [[ -n "${ALLOWED_SOURCE_RANGES:-}" ]] && args+=(-var="allowed_source_ranges=${ALLOWED_SOURCE_RANGES}")
  [[ -n "${ADMIN_MEMBERS:-}" ]] && args+=(-var="admin_members=${ADMIN_MEMBERS}")
  printf '%s\n' "${args[@]}"
}
