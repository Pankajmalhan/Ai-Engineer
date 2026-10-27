#!/usr/bin/env bash
# Step 5. Removes everything this module created -- VM, static IP, firewall, VPC,
# service account, and the password secret -- so nothing keeps billing. Not
# -auto-approve. Enabled APIs are left on.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

mapfile -t VARS < <(tf_vars)
terraform -chdir="$TERRAFORM_DIR" destroy -input=false "${VARS[@]}"
rm -f "$PASSWORD_FILE"
echo "Destroyed. (The model and TLS certificate lived on the VM's disk and are gone too.)"
