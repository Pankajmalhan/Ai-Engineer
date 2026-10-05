terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# The Cloud Run v2 `scaling.cpu_utilization` / `concurrency_utilization` fields are
# still Beta in the provider (see cloud_run_v2_service docs) -- only the resource that
# needs them is created with this provider alias, everything else uses the GA provider.
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
