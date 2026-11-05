# scripts/deploy_gateway.sh does this same sequence (apis create -> api-configs
# create -> gateways create) by hand, rendering gateway/openapi.yaml with `envsubst`
# first because the function's URL doesn't exist until *after* the function is
# deployed. Terraform doesn't need that two-pass dance: `templatefile()` below
# reads the same openapi.yaml and substitutes google_cloudfunctions2_function.rag.url
# directly from the resource graph, so Terraform sequences "deploy function, then
# wire the gateway to its real URL" for you via the dependency, not a shell script.
#
# The file's `${FUNCTION_URL}` placeholder was written for bash's `envsubst` -- it
# happens to also be valid Terraform template syntax (a `${...}` interpolation
# referencing a variable named FUNCTION_URL), so the exact same gateway/openapi.yaml
# serves both scripts/deploy_gateway.sh and this file, unmodified.
locals {
  rendered_openapi_spec = templatefile("${path.module}/../gateway/openapi.yaml", {
    FUNCTION_URL = google_cloudfunctions2_function.rag.url
    SERVICE_URL  = google_cloud_run_v2_service.svc.uri
  })
}

resource "google_service_account" "gateway_invoker" {
  account_id   = var.gateway_service_account_id
  display_name = "API Gateway invoker for ${var.function_name}"
}

# Bound on the function's underlying Cloud Run service: the cloudfunctions2 IAM API
# rejects roles/run.invoker with a 400.
resource "google_cloud_run_v2_service_iam_member" "fn_gateway_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloudfunctions2_function.rag.service_config[0].service
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.gateway_invoker.email}"
}

# Same grant for the plain Cloud Run service, so the gateway can front it too (/svc/*).
resource "google_cloud_run_v2_service_iam_member" "svc_gateway_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.svc.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.gateway_invoker.email}"
}

resource "google_api_gateway_api" "rag" {
  provider = google-beta
  project  = var.project_id
  api_id   = var.gateway_api_id
}

resource "google_api_gateway_api_config" "rag" {
  provider = google-beta
  project  = var.project_id
  api      = google_api_gateway_api.rag.api_id

  # API configs are immutable once created -- appending a content hash means a
  # change to the rendered spec (e.g. the function gets redeployed with a new URL,
  # or gateway/openapi.yaml itself changes) produces a *new* api_config resource
  # instead of trying to mutate one in place, which the API would reject.
  api_config_id = "${var.gateway_api_id}-${substr(md5(local.rendered_openapi_spec), 0, 10)}"

  openapi_documents {
    document {
      path     = "openapi.yaml"
      contents = base64encode(local.rendered_openapi_spec)
    }
  }

  gateway_config {
    backend_config {
      google_service_account = google_service_account.gateway_invoker.email
    }
  }

  # Paired with the api_config_id content hash above: create the new config (and
  # let the gateway below cut over to it) before destroying the old one, instead of
  # a delete-then-create that would 404 requests in between.
  lifecycle {
    create_before_destroy = true
  }
}

resource "google_api_gateway_gateway" "rag" {
  provider   = google-beta
  project    = var.project_id
  region     = var.region
  gateway_id = var.gateway_id
  api_config = google_api_gateway_api_config.rag.id
}
