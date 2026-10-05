# The comparison arm: identical app code to the function (function/app/), deployed
# as a plain Cloud Run service instead -- same resource type Week 9 used
# (google_cloud_run_v2_service), just pointed at an image built via a hand-written
# Dockerfile rather than buildpacks. This is what isolates "packaging path" as the
# only variable in this week's cold-start benchmark (see concept.md).
#
# No `google-beta` provider / scaling.cpu_utilization annotations here, unlike Week
# 9's cloud_run.tf -- this week's service doesn't need CPU-utilization-target
# autoscaling, only min/max instance *count*, which is GA on the `google` provider.
resource "google_cloud_run_v2_service" "svc" {
  name     = var.service_name
  location = var.region

  deletion_protection = false

  # No load balancer / Cloud Armor in front this week (see project/README.md's "out
  # of scope" section) -- direct public ingress, same as the function's `allUsers`
  # invoker grant.
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = var.service_min_instances
      max_instance_count = var.service_max_instances
    }

    containers {
      image = var.service_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      dynamic "env" {
        for_each = local.service_env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = { for e in local.secret_env_vars : e.name => e }
        content {
          name = env.value.name
          value_source {
            secret_key_ref {
              # Short secret id is enough for a same-project secret (see the
              # provider's own field description) -- no need for Week 9's
              # full-path-then-split() gymnastics here.
              secret  = env.value.secret
              version = env.value.version
            }
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  name     = google_cloud_run_v2_service.svc.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
