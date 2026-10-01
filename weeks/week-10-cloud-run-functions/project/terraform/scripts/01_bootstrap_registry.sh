#!/usr/bin/env bash
# Step 1 of a from-scratch deploy. Creates *only* the Artifact Registry repo, via a
# targeted apply, because of a real chicken-and-egg problem: the service's image
# (var.service_image) must already exist as a pushed image before `terraform apply`
# can create google_cloud_run_v2_service.svc, but you can't push an image into a
# repo that doesn't exist yet either.
#
# The function has no such problem -- google_cloudfunctions2_function builds its own
# image from source (function_source.tf) during a normal apply, no image variable
# needed -- so this targeted step exists purely for the service comparison arm.
#
# Idempotent: on every run after the first, this is a no-op ("no changes") apply, so
# it's safe -- and expected -- to run again on every future deployment too, not just
# the first one.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

terraform -chdir="$TERRAFORM_DIR" init -input=false

terraform -chdir="$TERRAFORM_DIR" apply -input=false \
  -target=google_artifact_registry_repository.app \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="artifact_repo_id=${REPO_ID}" \
  -var="service_image=placeholder" # unused by this targeted apply; the type just needs *a* string

echo
echo "Artifact Registry repo ready: ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_ID}"
echo "Next: ./02_build_and_push_service_image.sh"
