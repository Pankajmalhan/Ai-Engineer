#!/usr/bin/env bash
# Step 4. Waits for first-boot setup to finish (HTTPS /healthz answers), then runs the
# same endpoint checks as the manual-VPS path: 200 healthz, 401 without/with a wrong
# password, 200 with the right one, then a real generation.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

BASE_URL="$(terraform -chdir="$TERRAFORM_DIR" output -raw ollama_base_url)"
[[ -f "$PASSWORD_FILE" ]] || { echo "missing $PASSWORD_FILE (created by 01_bootstrap.sh)" >&2; exit 1; }

echo "Waiting for $BASE_URL/healthz (installing Ollama + pulling the model takes ~5-10 min)..."
for i in $(seq 1 90); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BASE_URL/healthz" || true)" == "200" ]]; then
    echo "up after ~$((i * 10))s"
    break
  fi
  [[ "$i" -eq 90 ]] && {
    echo "Timed out. Inspect first boot with:" >&2
    echo "  $(terraform -chdir="$TERRAFORM_DIR" output -raw startup_log_command)" >&2
    exit 1
  }
  sleep 10
done

EXPECT_GPU=0
[[ "$(terraform -chdir="$TERRAFORM_DIR" output -raw gpu_expected)" == "true" ]] && EXPECT_GPU=1

EXPECT_GPU="$EXPECT_GPU" BASIC_AUTH_USER="$BASIC_AUTH_USER" BASIC_AUTH_PASSWORD="$(cat "$PASSWORD_FILE")" \
  OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}" \
  "$TERRAFORM_DIR/../scripts/verify_endpoint.sh" "$BASE_URL"

echo
if [[ "$EXPECT_GPU" == "1" ]]; then
  echo
  echo "GPU machine: for utilisation proof from inside the VM run ./06_gpu_proof.sh"
fi

echo
echo "Add to project/.env:"
echo "  LLM_PROVIDER=ollama"
echo "  OLLAMA_BASE_URL=$BASE_URL"
echo "  OLLAMA_MODEL=${OLLAMA_MODEL:-llama3.2:3b}"
echo "  OLLAMA_BASIC_AUTH_USER=$BASIC_AUTH_USER"
echo "  OLLAMA_BASIC_AUTH_PASSWORD=\$(cat $PASSWORD_FILE)"
