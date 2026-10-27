locals {
  required_apis = [
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "iap.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_apis)

  service = each.value
  # Leave APIs enabled on destroy: other things in the project may depend on them.
  disable_on_destroy = false
}
