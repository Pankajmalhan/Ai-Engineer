#!/usr/bin/env bash
# Runs the on-VM proof that Ollama is really using the GPU: nvidia-smi, whether the model
# sits fully in VRAM, and peak GPU utilisation + tokens/s during a real generation.
# Goes through IAP (no public SSH). Needs the SSH/IAP permissions from README.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_common.sh

eval "$(terraform -chdir="$TERRAFORM_DIR" output -raw gpu_check_command)"
