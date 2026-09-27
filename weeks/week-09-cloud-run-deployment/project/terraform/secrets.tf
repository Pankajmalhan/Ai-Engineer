# The secret's own CONTAINER and VALUE are created out-of-band via `gcloud secrets
# create` / `gcloud secrets versions add` (see project README), deliberately not
# through Terraform -- a `google_secret_manager_secret_version` resource with
# `secret_data` set would put the real plaintext key into .tfstate, which is exactly
# the kind of leak this project has already been bitten by once (see notes.md). This
# file only grants the IAM access Cloud Run needs to *read* a secret that already
# exists -- no secret value ever appears here or in state.

# Cloud Run defaults to the project's Compute Engine default service account when
# `template.service_account` is left unset (as it is in cloud_run.tf) -- this data
# source resolves that account's email without hardcoding the project number.
data "google_compute_default_service_account" "default" {
}

# One grant per secret in var.secret_env_vars -- keyed by name for the same reason
# as cloud_run.tf's dynamic "env" block: stable per-entry diffs, and two entries
# referencing the same secret collapse to one grant instead of erroring on a
# duplicate IAM binding.
resource "google_secret_manager_secret_iam_member" "cloud_run_reads_secret" {
  for_each  = { for e in var.secret_env_vars : e.name => e }
  secret_id = split("/versions/", each.value.secret_version)[0]
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}
