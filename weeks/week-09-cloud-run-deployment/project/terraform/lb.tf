# HTTP only for now -- HTTPS needs a domain this project doesn't own (a managed SSL
# cert requires proving domain ownership). See project README for the exact 3 resources
# to add (google_compute_managed_ssl_certificate + google_compute_target_https_proxy +
# a :443 forwarding rule) once a real domain is pointed at lb_ip_address.
resource "google_compute_global_address" "lb_ip" {
  name = "${var.service_name}-lb-ip"
}

resource "google_compute_url_map" "app" {
  name            = "${var.service_name}-url-map"
  default_service = google_compute_backend_service.app.id
}

resource "google_compute_target_http_proxy" "app" {
  name    = "${var.service_name}-http-proxy"
  url_map = google_compute_url_map.app.id
}

resource "google_compute_global_forwarding_rule" "app" {
  name                  = "${var.service_name}-fwd-rule"
  ip_address            = google_compute_global_address.lb_ip.address
  ip_protocol           = "TCP"
  port_range            = "80"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  target                = google_compute_target_http_proxy.app.id
}
