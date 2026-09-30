#!/usr/bin/env bash
# Tears down everything this module created -- function, service, gateway, Artifact
# Registry repo (images included, see ../README.md's note on that), GCS source
# bucket, IAM bindings. Not -auto-approve, for the same reason 04_apply.sh isn't.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

if [[ ! -f "$LAST_IMAGE_FILE" ]]; then
  echo "No .last_image -- pass the same service_image value destroy last saw, or run" >&2
  echo "02_build_and_push_service_image.sh again first so the variable resolves." >&2
  exit 1
fi

mapfile -t VARS < <(tf_vars)
terraform -chdir="$TERRAFORM_DIR" destroy -input=false "${VARS[@]}"
