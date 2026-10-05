# The Terraform-native way to deploy a Cloud Run function (2nd gen). Note the
# resource name: `google_cloudfunctions2_function` -- the provider never renamed this
# to match Google's own Aug 2026 "Cloud Run functions" rebrand (see resources.md);
# it is the same resource type, same API, just an older name that stuck in the
# provider's own schema.
resource "google_cloudfunctions2_function" "rag" {
  name        = var.function_name
  location    = var.region
  description = "Week 10 Northwind RAG endpoint, Cloud Run function (2nd gen)."

  build_config {
    runtime           = "python313"
    entry_point       = "rag_chat"
    docker_repository = google_artifact_registry_repository.app.id

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source.name
      }
    }
  }

  service_config {
    min_instance_count = var.function_min_instances
    max_instance_count = var.function_max_instances
    available_memory   = "512M"
    timeout_seconds    = 60

    # Not secret: which deployment this is (Langfuse tag + environment), and the Langfuse URL.
    environment_variables = local.function_env_vars

    # Same shape Week 9's cloud_run.tf uses for its `env` dynamic block: keyed by
    # name so two entries never silently collide, and each secret's IAM grant lives
    # in secrets.tf, not here -- this block only wires the reference.
    dynamic "secret_environment_variables" {
      for_each = { for e in local.secret_env_vars : e.name => e }
      content {
        key        = secret_environment_variables.value.name
        project_id = var.project_id
        secret     = secret_environment_variables.value.secret
        version    = secret_environment_variables.value.version
      }
    }
  }
}

# Matches this week's actual deployment (--allow-unauthenticated), so the raw
# function URL stays directly curl-able for the benchmark script alongside the
# gateway. See concept.md's API Gateway answer for why you'd remove this `allUsers`
# grant in a real deployment and force all public traffic through the gateway instead.
# Bound on the function's underlying Cloud Run service: the cloudfunctions2 IAM API
# rejects roles/run.invoker with a 400.
resource "google_cloud_run_v2_service_iam_member" "fn_public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloudfunctions2_function.rag.service_config[0].service
  role     = "roles/run.invoker"
  member   = "allUsers"
}
