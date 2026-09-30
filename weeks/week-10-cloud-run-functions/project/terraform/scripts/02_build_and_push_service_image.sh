#!/usr/bin/env bash
# Step 2. Builds ../../function (the app code + function/Dockerfile -- the *service*
# packaging path, not buildpacks) via Cloud Build, and pushes it into the repo
# 01_bootstrap_registry.sh created.
#
# Tagged with the current git SHA, not a fixed "v1" or mutable "latest" -- same
# reasoning as Week 9's scripts/build_and_push.sh: Terraform diffs var.service_image
# as a plain string, so re-pushing new content under the *same* tag would leave
# Terraform seeing "no change" and never deploy the new revision on a future
# deployment. A SHA-tagged image guarantees a code change produces a new value.
#
# Writes the pushed image ref to .last_image (gitignored -- see ../.gitignore) for
# 03_plan.sh / 04_apply.sh to pick up automatically via _common.sh's tf_vars().
# Re-run this every time function/ changes and you want to redeploy the service arm --
# it's exactly as safe to run on deployment #20 as on deployment #1.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

TAG="$(git -C "$TERRAFORM_DIR" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
if ! git -C "$TERRAFORM_DIR" diff --quiet -- "$FUNCTION_DIR" 2>/dev/null; then
  TAG="${TAG}-dirty"
fi
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_ID}/northwind-rag-svc-tf:${TAG}"

echo "Building and pushing ${IMAGE} via Cloud Build"
gcloud builds submit --tag="$IMAGE" --project="$PROJECT_ID" "$FUNCTION_DIR"

echo "$IMAGE" > "$LAST_IMAGE_FILE"
echo
echo "Wrote $LAST_IMAGE_FILE -> $IMAGE"
echo "Next: ./03_plan.sh"
