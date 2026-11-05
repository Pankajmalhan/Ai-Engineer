output "cloud_run_url" {
  description = "Direct *.run.app URL. Rejected at ingress unless the request came through the LB -- useful for `gcloud run services describe`, not for curl."
  value       = google_cloud_run_v2_service.app.uri
}

output "load_balancer_ip" {
  description = "Public IP to point a domain at, or to curl directly: http://<this>/health"
  value       = google_compute_global_address.lb_ip.address
}

output "artifact_registry_repo" {
  description = "Push images here: <region>-docker.pkg.dev/<project>/<repo_id>"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}
