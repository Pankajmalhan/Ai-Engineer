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
    Default g2-standard-4 = 4 vCPU, 16 GB RAM and ONE NVIDIA L4 (24 GB VRAM). G2/A2/A3
    machine types include their GPU automatically -- leave gpu_type empty for them.
    For a CPU-only run use e.g. e2-medium (the Week 11 baseline) or c3-standard-8.
  EOT
  type        = string
  default     = "g2-standard-4"
}

variable "gpu_type" {
  description = <<-EOT
    Only for N1 machine types, which need an explicit accelerator (e.g.
    machine_type = "n1-standard-4", gpu_type = "nvidia-tesla-t4"). Leave empty for G2/A2/A3
    (GPU is part of the machine type) and for CPU-only machines.
  EOT
  type        = string
  default     = ""
}

variable "gpu_count" {
  description = "Number of accelerators when gpu_type is set."
  type        = number
  default     = 1
}

variable "use_spot" {
  description = <<-EOT
    Spot VM: roughly 60-90% cheaper, but Google can reclaim it at any time (the VM is
    stopped, not deleted; start it again). Fine for experiments, not for serving.
  EOT
  type        = bool
  default     = false
}

variable "secure_boot" {
  description = <<-EOT
    Shielded-VM Secure Boot. null = automatic: ON for CPU VMs, OFF for GPU VMs, because
    the NVIDIA kernel module installed by DKMS is unsigned and Secure Boot would refuse to
    load it (vTPM and integrity monitoring stay on either way).
  EOT
  type        = bool
  default     = null
}

variable "ollama_num_parallel" {
  description = "OLLAMA_NUM_PARALLEL. null = automatic: 1 on CPU (parallel requests only compete for cores), 4 on GPU (a GPU batches concurrent requests well)."
  type        = number
  default     = null
}

variable "ollama_context_length" {
  description = "OLLAMA_CONTEXT_LENGTH: tokens of context per request slot. KV-cache memory is roughly 115 KB per token for a 3B model, multiplied by the number of parallel slots."
  type        = number
  default     = 4096
}

variable "boot_disk_gb" {
  description = "OS + NVIDIA driver/CUDA packages + model files. 50 GB leaves room for the driver build and several models."
  type        = number
  default     = 50
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

variable "nginx_rate_limit_per_second" {
  description = <<-EOT
    Nginx limit_req rate per client IP (requests/second). The default 5 is a sensible abuse
    brake for CPU inference, but a GPU answers in ~0.5 s so a load test exceeds it and gets
    503s. Raise it (e.g. 50) when benchmarking; lower it again for anything exposed.
  EOT
  type        = number
  default     = 5
}

variable "nginx_rate_limit_burst" {
  description = "Extra requests Nginx serves immediately above the rate before returning 503."
  type        = number
  default     = 10
}
