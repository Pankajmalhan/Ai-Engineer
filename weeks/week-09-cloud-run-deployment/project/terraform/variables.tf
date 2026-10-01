variable "project_id" {
  description = "GCP project to deploy into."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Artifact Registry, and the backend service's NEG."
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "northwind-rag-week9"
}

variable "artifact_repo_id" {
  description = "Artifact Registry repository id (Docker format) the service's image lives in."
  type        = string
  default     = "northwind-rag"
}

variable "image" {
  description = <<-EOT
    Full image reference to deploy, e.g.
    us-central1-docker.pkg.dev/<project>/northwind-rag/app:<tag>.
    Set this on every apply (scripts/deploy.sh reads it from .last_image, written by
    scripts/build_and_push.sh) -- Terraform is the single source of truth for which
    image tag is actually running, not a manual `gcloud run deploy`.
  EOT
  type        = string
}

variable "min_instances" {
  description = "Minimum warm Cloud Run instances (>0 means always-on / instance-based billing -- see min_instance_count in the provider docs)."
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum Cloud Run instances this service is allowed to scale to."
  type        = number
  default     = 10
}

variable "cpu_utilization_target" {
  description = "CPU utilization threshold (0.1-0.95) that triggers scale-out, per instance."
  type        = number
  default     = 0.6
}

variable "container_cpu" {
  description = "vCPUs allocated per instance. Only '1','2','4','6','8' are valid."
  type        = string
  default     = "1"
}

variable "container_memory" {
  description = "Memory allocated per instance."
  type        = string
  default     = "512Mi"
}

variable "secret_env_vars" {
  description = <<-EOT
    Environment variables to inject into the container from Secret Manager, e.g.:

      [
        { name = "OPENAI_API_KEY",     secret_version = "projects/p/secrets/openai-api-key/versions/latest" },
        { name = "BRAINTRUST_API_KEY", secret_version = "projects/p/secrets/braintrust-api-key/versions/latest" },
      ]

    Each secret must already exist (see project README -- `gcloud secrets create`) --
    Terraform only wires the reference and grants read access (secrets.tf), it never
    creates or manages a secret's actual value, so no plaintext key ever lands in
    .tfstate. Left empty ([]), the service starts with none of these set -- /health
    still works, endpoints needing a missing key will error, which is enough to
    validate the deploy pipeline itself before wiring real secrets.
  EOT
  type = list(object({
    name           = string
    secret_version = string
  }))
  default = []
}
