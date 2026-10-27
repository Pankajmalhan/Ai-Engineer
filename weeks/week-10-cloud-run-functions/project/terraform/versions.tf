terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    # API Gateway's resources are documented against the beta provider (see gateway.tf)
    # -- same reasoning as Week 9's cloud_run_v2_service scaling block needing google-beta.
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    # Only used to zip function/ into the source archive Cloud Functions gen2 requires
    # (see function_source.tf) -- gcloud run deploy --source hides this step from you;
    # a plain google_cloudfunctions2_function resource does not.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
