variable "project_id" {
  description = "GCP project to deploy into."
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "name_prefix" {
  description = "Prefix for every resource this module creates."
  type        = string
  default     = "ollama-edge"
}

variable "machine_type" {
  description = <<-EOT
    e2-medium (2 vCPU, 4 GB) is the smallest size that holds llama3.2:3b (~2 GB of
    weights) with headroom for the KV cache, Nginx and the OS -- see concept.md section 2.
    Use e2-standard-2 (8 GB) for 7B-class models (mistral).
  EOT
  type        = string
  default     = "e2-medium"
}

variable "boot_disk_gb" {
  description = "OS + model files. 30 GB leaves room for several pulled models."
  type        = number
  default     = 30
}

variable "ollama_model" {
  description = "Model pulled onto the VM at first boot."
  type        = string
  default     = "llama3.2:3b"
}

variable "domain_name" {
  description = <<-EOT
    DNS name you have pointed (A record) at the static IP. Leave empty to use the
    free <dashed-ip>.sslip.io name, which resolves to the IP and works with Let's Encrypt.
  EOT
  type        = string
  default     = ""
}

variable "le_email" {
  description = "Email for Let's Encrypt expiry notices."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.le_email))
    error_message = "le_email must look like an email address."
  }
}

variable "basic_auth_user" {
  description = "Username Nginx accepts. The password lives in Secret Manager, never in Terraform."
  type        = string
  default     = "rag"
}

variable "basic_auth_secret_id" {
  description = "Secret Manager secret holding the basic-auth password (value added by scripts/01_bootstrap.sh)."
  type        = string
  default     = "ollama-basic-auth-password"
}

variable "allowed_source_ranges" {
  description = <<-EOT
    CIDR ranges allowed to reach HTTPS (443). 0.0.0.0/0 relies on basic auth alone;
    narrow this to your own IP (e.g. ["203.0.113.7/32"]) for a much stronger posture.
    Port 80 is deliberately NOT governed by this: Let's Encrypt validates from
    arbitrary addresses, so restricting 80 would break issuance and renewal.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = alltrue([for c in var.allowed_source_ranges : can(cidrhost(c, 0))])
    error_message = "Every entry must be a valid CIDR range."
  }
}

variable "admin_members" {
  description = <<-EOT
    IAM members allowed to SSH to the VM (through IAP, with OS Login), e.g.
    ["user:you@example.com"]. Project owners already can; this is for everyone else.
  EOT
  type        = list(string)
  default     = []
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.0.0/24"
}
