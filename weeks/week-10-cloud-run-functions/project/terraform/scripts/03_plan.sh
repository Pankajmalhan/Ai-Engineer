#!/usr/bin/env bash
# Step 3. Shows what would change -- creates nothing. Run this before every apply,
# first deployment or the hundredth: it's how you catch "oh, that's not what I meant"
# before Terraform acts on it.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

if [[ ! -f "$LAST_IMAGE_FILE" ]]; then
  echo "No .last_image -- run ./02_build_and_push_service_image.sh first" >&2
  exit 1
fi

terraform -chdir="$TERRAFORM_DIR" init -input=false
mapfile -t VARS < <(tf_vars)
terraform -chdir="$TERRAFORM_DIR" plan -input=false "${VARS[@]}"
