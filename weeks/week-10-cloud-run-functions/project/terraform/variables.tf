variable "project_id" {
  description = "GCP project to deploy into."
  type        = string
}

variable "region" {
  description = "Region for Artifact Registry, the function, the service, and the gateway."
  type        = string
  default     = "us-central1"
}

variable "artifact_repo_id" {
  description = "Artifact Registry (Docker format) repository id both the function's buildpacks image and the service's image live in."
  type        = string
  default     = "northwind-rag-tf"
}

variable "function_name" {
  description = <<-EOT
    Cloud Run function name. Defaults to a name distinct from the *_fn service this
    week's scripts/ path already deployed by hand (northwind-rag-fn) -- both can exist
    side by side without colliding. Point this at "northwind-rag-fn" instead only after
    running scripts/teardown.sh (or pass distinct names and tear down manually).
  EOT
  type        = string
  default     = "northwind-rag-fn-tf"
}

variable "function_min_instances" {
  description = "See concept.md's routing-threshold decision -- 1 eliminates the recurring cold-start tax for a user-facing endpoint."
  type        = number
  default     = 1
}

variable "function_max_instances" {
  type    = number
  default = 10
}

variable "service_name" {
  description = "Cloud Run service (comparison arm) name -- see function_name's note on avoiding collisions."
  type        = string
  default     = "northwind-rag-svc-tf"
}

variable "service_image" {
  description = <<-EOT
    Full image reference for the *service* comparison arm, e.g.
    us-central1-docker.pkg.dev/<project>/northwind-rag-tf/northwind-rag-svc:v1.
    Terraform cannot build this itself (see function_source.tf's comment on why the
    function side is different) -- build and push it yourself first, e.g.:
      gcloud builds submit --tag=<this value> ../function
    then pass it here via -var or terraform.tfvars.
  EOT
  type        = string
}

variable "service_min_instances" {
  type    = number
  default = 0
}

variable "service_max_instances" {
  type    = number
  default = 10
}

variable "gateway_api_id" {
  type    = string
  default = "northwind-rag-api-tf"
}

variable "gateway_id" {
  type    = string
  default = "northwind-rag-gateway-tf"
}

variable "gateway_service_account_id" {
  description = "Service account API Gateway uses to call the function -- must be <= 30 chars, matching GCP's service account id limit."
  type        = string
  default     = "apigw-rag-invoker-tf"
}

variable "secret_env_vars" {
  description = <<-EOT
    Secrets injected into both the function and the service from Secret Manager, e.g.:

      [{ name = "OPENAI_API_KEY", secret = "openai-api-key", version = "latest" }]

    Each secret must already exist (see project README's "Deploy for real" section --
    `gcloud secrets create`). Terraform only wires the reference and grants read
    access (secrets.tf); it never creates or manages a secret's actual value, so no
    plaintext key ever lands in .tfstate -- same rule Week 9's terraform/secrets.tf
    follows, for the same reason.
  EOT
  type = list(object({
    name    = string
    secret  = string
    version = optional(string, "latest")
  }))
  default = [
    { name = "OPENAI_API_KEY", secret = "openai-api-key", version = "latest" },
  ]
}

variable "enable_langfuse" {
  description = <<-EOT
    Send traces from BOTH the function and the service to Langfuse. Adds LANGFUSE_PUBLIC_KEY /
    LANGFUSE_SECRET_KEY (from Secret Manager secrets `langfuse-public-key` /
    `langfuse-secret-key`, which must already exist) and LANGFUSE_BASE_URL. Note the cold-start
    tradeoff in concept.md: the Langfuse SDK is imported on the first traced request.
  EOT
  type        = bool
  default     = false
}

variable "langfuse_base_url" {
  description = "Langfuse server URL used when enable_langfuse is true (a Langfuse on your laptop is not reachable from Cloud Run)."
  type        = string
  default     = "https://cloud.langfuse.com"
}
