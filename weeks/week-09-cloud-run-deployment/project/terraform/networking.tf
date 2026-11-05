# Serverless NEG: how the external LB's backend service reaches a Cloud Run service --
# Cloud Run has no VM/instance-group backend of its own to point a NEG at otherwise.
resource "google_compute_region_network_endpoint_group" "cloud_run_neg" {
  name                  = "${var.service_name}-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.app.name
  }
}

# No `health_checks` block: serverless NEG backends don't support/require one -- Cloud
# Run manages its own instance health, the LB just proxies to whichever revision is
# currently serving traffic.
resource "google_compute_backend_service" "app" {
  name                  = "${var.service_name}-backend"
  protocol              = "HTTP"
  port_name             = "http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = 30

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg.id
  }

  security_policy = google_compute_security_policy.app.id
}
