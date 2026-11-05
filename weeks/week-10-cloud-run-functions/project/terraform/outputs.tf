output "function_url" {
  description = "Direct *.run.app / *.a.run.app URL of the Cloud Run function -- curl-able directly, same as northwind-rag-fn."
  value       = google_cloudfunctions2_function.rag.url
}

output "service_url" {
  description = "Direct URL of the comparison Cloud Run service."
  value       = google_cloud_run_v2_service.svc.uri
}

output "gateway_hostname" {
  description = "API Gateway's hostname -- try GET https://<this>/health or POST https://<this>/chat."
  value       = google_api_gateway_gateway.rag.default_hostname
}

output "artifact_registry_repo" {
  description = "Push the service's image here: <region>-docker.pkg.dev/<project>/<repo_id>"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}
