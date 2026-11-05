#!/usr/bin/env bash
# Step 4. The one command in this whole directory that actually changes what's
# running. Deliberately *not* -auto-approve -- Terraform will print its own plan and
# ask you to type "yes", which is the habit worth keeping even once this feels
# routine: reviewing before every apply, not just the first one.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

if [[ ! -f "$LAST_IMAGE_FILE" ]]; then
  echo "No .last_image -- run ./02_build_and_push_service_image.sh first" >&2
  exit 1
fi

terraform -chdir="$TERRAFORM_DIR" init -input=false
mapfile -t VARS < <(tf_vars)
terraform -chdir="$TERRAFORM_DIR" apply -input=false "${VARS[@]}"

echo
echo "function_url:      $(terraform -chdir="$TERRAFORM_DIR" output -raw function_url)"
echo "service_url:        $(terraform -chdir="$TERRAFORM_DIR" output -raw service_url)"
echo "gateway_hostname:   $(terraform -chdir="$TERRAFORM_DIR" output -raw gateway_hostname)"
