# The VM runs as its own service account, not the project's default Compute account
# (which is Editor-level by default). This one can do exactly one thing: read the
# basic-auth password secret.
resource "google_service_account" "vm" {
  account_id   = "${var.name_prefix}-vm"
  display_name = "Ollama edge VM"

  depends_on = [google_project_service.required]
}

# Only the secret's *container* is managed here. The password value is added out of
# band by scripts/01_bootstrap.sh (`gcloud secrets versions add`) -- a
# google_secret_manager_secret_version with secret_data would put the plaintext into
# .tfstate. Same rule as Weeks 9 and 10.
resource "google_secret_manager_secret" "basic_auth" {
  secret_id = var.basic_auth_secret_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "vm_reads_password" {
  secret_id = google_secret_manager_secret.basic_auth.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.vm.email}"
}

# Human admins: OS Login (IAM-managed SSH identity) plus permission to open an IAP
# tunnel -- both scoped to this one instance, not the project.
resource "google_compute_instance_iam_member" "admin_os_login" {
  for_each = toset(var.admin_members)

  zone          = var.zone
  instance_name = google_compute_instance.ollama.name
  role          = "roles/compute.osAdminLogin"
  member        = each.value
}

resource "google_iap_tunnel_instance_iam_member" "admin_tunnel" {
  for_each = toset(var.admin_members)

  zone     = var.zone
  instance = google_compute_instance.ollama.name
  role     = "roles/iap.tunnelResourceAccessor"
  member   = each.value
}
