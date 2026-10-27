# A dedicated VPC instead of `default`: the default network ships permissive rules
# (open SSH/RDP/ICMP from anywhere) that would sit next to ours.
resource "google_compute_network" "vpc" {
  name                    = "${var.name_prefix}-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "subnet" {
  name                     = "${var.name_prefix}-subnet"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

# The address clients (and the sslip.io name) point at. Reserved separately from the
# VM so it survives the VM being replaced -- the URL in your .env stays valid.
resource "google_compute_address" "ip" {
  name   = "${var.name_prefix}-ip"
  region = var.region

  depends_on = [google_project_service.required]
}

# --- Ingress (VPC ingress is deny-by-default; these are the only holes) -------------

# 80: Let's Encrypt's HTTP-01 validators come from arbitrary addresses, so this cannot
# be range-restricted. After issuance Nginx only redirects to 443 here.
resource "google_compute_firewall" "http" {
  name      = "${var.name_prefix}-allow-http"
  network   = google_compute_network.vpc.name
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }
  source_ranges = ["0.0.0.0/0"]
  target_tags   = [local.network_tag]
}

# 443: the actual API. This is the rule to tighten with allowed_source_ranges.
resource "google_compute_firewall" "https" {
  name      = "${var.name_prefix}-allow-https"
  network   = google_compute_network.vpc.name
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
  source_ranges = var.allowed_source_ranges
  target_tags   = [local.network_tag]
}

# SSH only from Google's IAP forwarding range: port 22 is never reachable from the
# internet. Access is `gcloud compute ssh --tunnel-through-iap`, authorised by IAM.
resource "google_compute_firewall" "iap_ssh" {
  name      = "${var.name_prefix}-allow-iap-ssh"
  network   = google_compute_network.vpc.name
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["35.235.240.0/20"]
  target_tags   = [local.network_tag]
}

# There is intentionally no rule for 11434: Ollama listens on loopback only and the
# firewall would drop it anyway.
