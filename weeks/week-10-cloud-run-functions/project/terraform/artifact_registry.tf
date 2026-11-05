# One shared repo for both images -- the function's buildpacks build (function.tf)
# and the service's hand-built image (pushed out-of-band, see variables.tf's
# service_image comment). `gcloud run deploy --source` would auto-create a repo
# named `cloud-run-source-deploy` if you let it; declaring it here instead means
# Terraform, not an implicit side effect of a deploy command, owns its lifecycle.
resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = var.artifact_repo_id
  format        = "DOCKER"
  description   = "Container images for the Week 10 Cloud Run function + service comparison."
}
