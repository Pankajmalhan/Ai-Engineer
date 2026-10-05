locals {
  network_tag = "${var.name_prefix}-vm"

  # G2/A2/A3/G4 machine types ship with their GPU; N1 needs an explicit accelerator.
  has_gpu      = var.gpu_type != "" || can(regex("^(g2|a2|a3|g4)-", var.machine_type))
  num_parallel = var.ollama_num_parallel != null ? var.ollama_num_parallel : (local.has_gpu ? 4 : 1)
  secure_boot  = var.secure_boot != null ? var.secure_boot : !local.has_gpu

  # sslip.io maps <dashed-ip>.sslip.io to that IP, so Let's Encrypt can issue a real
  # certificate with no domain purchase.
  server_name = var.domain_name != "" ? var.domain_name : "${replace(google_compute_address.ip.address, ".", "-")}.sslip.io"

  startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    server_name     = local.server_name
    le_email        = var.le_email
    ollama_model    = var.ollama_model
    expect_gpu      = local.has_gpu
    num_parallel    = local.num_parallel
    context_length  = var.ollama_context_length
    basic_auth_user = var.basic_auth_user
    secret_id       = google_secret_manager_secret.basic_auth.secret_id
    project_id      = var.project_id
    nginx_conf      = replace(replace(replace(file("${path.module}/../deploy/ollama.nginx.conf"), "__SERVER_NAME__", local.server_name), "__RATE__", tostring(var.nginx_rate_limit_per_second)), "__BURST__", tostring(var.nginx_rate_limit_burst))
  })
}

resource "google_compute_instance" "ollama" {
  name         = "${var.name_prefix}-vm"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = [local.network_tag]

  # Lets Terraform stop the VM to change machine_type / service account in place.
  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.boot_disk_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id

    access_config {
      nat_ip = google_compute_address.ip.address
    }
  }

  service_account {
    email = google_service_account.vm.email
    # The scope is a coarse outer gate; IAM (iam.tf) is what actually limits access.
    scopes = ["cloud-platform"]
  }

  dynamic "guest_accelerator" {
    for_each = var.gpu_type != "" ? [1] : []
    content {
      type  = var.gpu_type
      count = var.gpu_count
    }
  }

  # GPU VMs cannot live-migrate, so host maintenance must TERMINATE (and then restart).
  scheduling {
    on_host_maintenance         = (local.has_gpu || var.use_spot) ? "TERMINATE" : "MIGRATE"
    automatic_restart           = !var.use_spot
    preemptible                 = var.use_spot
    provisioning_model          = var.use_spot ? "SPOT" : "STANDARD"
    instance_termination_action = var.use_spot ? "STOP" : null
  }

  shielded_instance_config {
    enable_secure_boot          = local.secure_boot
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    # SSH identity comes from IAM (OS Login), never from key files in metadata.
    enable-oslogin = "TRUE"
    # Ignore any project-wide SSH keys someone added to the project.
    block-project-ssh-keys = "TRUE"
  }

  metadata_startup_script = local.startup_script

  depends_on = [
    google_secret_manager_secret_iam_member.vm_reads_password,
  ]
}
