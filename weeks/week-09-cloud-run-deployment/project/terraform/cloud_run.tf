# google-beta + launch_stage=BETA are required specifically for the scaling block's
# cpu_utilization/concurrency_utilization fields (still Beta in the provider as of this
# writing -- see terraform-provider-google's cloud_run_v2_service docs).
resource "google_cloud_run_v2_service" "app" {
  provider = google-beta
  name     = var.service_name
  location = var.region

  launch_stage        = "BETA"
  deletion_protection = false

  # Traffic only arrives through the external LB's serverless NEG (see lb.tf) -- direct
  # *.run.app requests are rejected. Cloud Armor in front of the LB is the actual edge,
  # not Cloud Run's own ingress control, so this closes the bypass-the-WAF path.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    # CPU/concurrency scaling *targets* aren't first-class fields on this provider's
    # `scaling` block (verified against the installed hashicorp/google-beta v6.50
    # schema -- terraform-provider-google's own docs show them as upcoming fields, but
    # they don't exist yet); Cloud Run instead reads them off these template
    # annotations, which is also exactly what `gcloud beta run services update
    # --scaling-cpu-target` sets under the hood. min/max instance *count*, by contrast,
    # is a real field, in the `scaling` block below.
    annotations = {
      "run.googleapis.com/scaling-cpu-target"         = format("%.2f", var.cpu_utilization_target)
      "run.googleapis.com/scaling-concurrency-target" = "0.60"
    }

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        cpu_idle          = true
        startup_cpu_boost = true
        limits = {
          cpu    = var.container_cpu
          memory = var.container_memory
        }
      }

      # Keyed by name (not a plain list) so Terraform's diff is stable per secret --
      # adding/removing one entry in var.secret_env_vars only touches that entry, and
      # two entries accidentally given the same name collapse to one at plan time
      # instead of both reaching the API (which Cloud Run would reject outright; see
      # the reserved-env-name error this project already hit once for PORT).
      dynamic "env" {
        for_each = { for e in var.secret_env_vars : e.name => e }
        content {
          name = env.value.name
          value_source {
            secret_key_ref {
              secret  = split("/versions/", env.value.secret_version)[0]
              version = split("/versions/", env.value.secret_version)[1]
            }
          }
        }
      }
    }
  }
}

# The LB forwards end-user requests unauthenticated as far as IAM is concerned --
# Cloud Armor (cloud_armor.tf) is the access-control layer in front of this service, not
# per-caller IAM. Public exposure is therefore intentional here, not an oversight.
resource "google_cloud_run_v2_service_iam_member" "public_via_lb" {
  provider = google-beta
  name     = google_cloud_run_v2_service.app.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
