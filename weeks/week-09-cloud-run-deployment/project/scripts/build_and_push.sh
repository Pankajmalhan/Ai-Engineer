#!/usr/bin/env bash
# Builds the app image and pushes it to Artifact Registry, tagged with the current git
# SHA (not `latest` -- Terraform pins the exact image it deployed via var.image, and a
# mutable tag would make `terraform plan` unable to tell whether the running image
# actually matches what's in state).
#
# Requires: docker, gcloud authenticated with Artifact Registry push permission on
# PROJECT_ID/REGION/REPO_ID. Writes the pushed image ref to .last_image (gitignored --
# it's this run's output, not tracked config) for scripts/deploy.sh to consume.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPO_ID="${REPO_ID:-northwind-rag}"
SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TAG="$(git -C "$SERVICE_DIR" rev-parse --short HEAD)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_ID}/app:${TAG}"

echo "Building ${IMAGE}"
# --platform=linux/amd64 is required regardless of the build machine's own architecture
# -- Cloud Run only runs linux/amd64 containers, and `docker build` otherwise defaults
# to the host's native arch (arm64 on Apple Silicon), producing an image Cloud Run
# rejects outright. Docker Desktop cross-builds this via QEMU emulation automatically.
docker build --platform=linux/amd64 -t "$IMAGE" "$SERVICE_DIR"

echo "Configuring docker auth for ${REGION}-docker.pkg.dev"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "Pushing ${IMAGE}"
docker push "$IMAGE"

echo "$IMAGE" > "$SERVICE_DIR/.last_image"
echo "Wrote $SERVICE_DIR/.last_image -> $IMAGE"
