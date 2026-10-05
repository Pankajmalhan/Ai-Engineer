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

output "gpu_expected" {
  description = "true when the machine type / gpu_type implies a GPU (drives the GPU checks in the verify scripts)."
  value       = local.has_gpu
}

output "gpu_check_command" {
  description = "Run on the VM through IAP: nvidia-smi, where the model is placed, and (with --load) GPU utilisation during a generation."
  value       = "gcloud compute ssh ${google_compute_instance.ollama.name} --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap --command='sudo ollama-gpu-check --load'"
}
