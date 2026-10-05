# Same rule as Week 9's terraform/secrets.tf, for the same reason: the secret's own
# value is created out-of-band via `gcloud secrets create` (see project README),
# never through a google_secret_manager_secret_version resource with secret_data set
# -- that would put the real plaintext key into .tfstate. This file only grants read
# access to a secret that already exists.

# Both the function and the service default to the project's Compute Engine default
# service account (neither function.tf nor service.tf sets service_account_email /
# a custom template.service_account) -- this data source resolves that account's
# email without hardcoding the project number.
data "google_compute_default_service_account" "default" {
}

resource "google_secret_manager_secret_iam_member" "reads_secret" {
  for_each  = { for e in local.secret_env_vars : e.name => e }
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}
