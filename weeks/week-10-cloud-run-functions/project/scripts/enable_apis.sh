#!/usr/bin/env bash
# One-time per project. Safe to re-run -- gcloud services enable is idempotent.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"

gcloud services enable \
  run.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  apigateway.googleapis.com \
  servicecontrol.googleapis.com \
  servicemanagement.googleapis.com \
  secretmanager.googleapis.com \
  monitoring.googleapis.com \
  --project="$PROJECT_ID"
