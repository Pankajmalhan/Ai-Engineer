output "ollama_ip" {
  description = "Static external IP of the VM."
  value       = google_compute_address.ip.address
}

output "ollama_base_url" {
  description = "Put this in OLLAMA_BASE_URL (.env)."
  value       = "https://${local.server_name}"
}

output "ssh_command" {
  description = "SSH with no public port 22: through IAP, authorised by IAM."
  value       = "gcloud compute ssh ${google_compute_instance.ollama.name} --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap"
}

output "startup_log_command" {
  description = "Watch first-boot progress (Ollama install, model pull, certificate)."
  value       = "gcloud compute instances get-serial-port-output ${google_compute_instance.ollama.name} --zone=${var.zone} --project=${var.project_id} | tail -40"
}
