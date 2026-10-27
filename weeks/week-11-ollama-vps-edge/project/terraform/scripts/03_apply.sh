#!/usr/bin/env bash
# Step 3. Creates the network, firewall, service account, static IP and VM. Not
# -auto-approve: Terraform prints the plan and asks you to type "yes".
#
# The VM then spends a few minutes installing Ollama, pulling the model and getting a
# certificate -- `terraform apply` returns before that finishes. Run 04 next.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

terraform -chdir="$TERRAFORM_DIR" init -input=false
mapfile -t VARS < <(tf_vars)
terraform -chdir="$TERRAFORM_DIR" apply -input=false "${VARS[@]}" "$@"

echo
echo "ollama_base_url: $(terraform -chdir="$TERRAFORM_DIR" output -raw ollama_base_url)"
echo "Next: ./04_wait_and_verify.sh"
