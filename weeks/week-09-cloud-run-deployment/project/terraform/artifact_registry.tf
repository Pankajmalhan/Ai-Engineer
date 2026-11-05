resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = var.artifact_repo_id
  format        = "DOCKER"
  description   = "Container images for the Week 9 Northwind RAG service."
}
