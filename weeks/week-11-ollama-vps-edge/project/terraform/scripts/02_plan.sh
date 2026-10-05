#!/usr/bin/env bash
# Step 2. Shows what would change; creates nothing. Read it before every apply.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

terraform -chdir="$TERRAFORM_DIR" init -input=false
mapfile -t VARS < <(tf_vars)
terraform -chdir="$TERRAFORM_DIR" plan -input=false "${VARS[@]}"
