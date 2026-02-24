# /Users/jonathanhuang/Developer/cat-ai-factory/infra/terraform/gpu_worker.tf

# ------------------------------------------------------------------------------
# GPU WORKER NODE INFRASTRUCTURE (PHASE 12)
# ------------------------------------------------------------------------------

resource "google_compute_instance_template" "worker_gpu" {
  name_prefix  = "caf-worker-gpu-"
  machine_type = "g2-standard-4" # 4 vCPUs, 16GB RAM, 1x L4 GPU (24GB VRAM)

  disk {
    source_image = "projects/deeplearning-platform-release/global/images/family/common-cu121-debian-11-py310"
    auto_delete  = true
    boot         = true
    disk_size_gb = 100
    disk_type    = "pd-balanced"
  }

  guest_accelerator {
    type  = "nvidia-l4"
    count = 1
  }

  network_interface {
    network = "default" # TODO: Map to dedicated CAF VPC
    access_config {}
  }

  scheduling {
    on_host_maintenance = "TERMINATE" # GPU instances cannot be migrated
    automatic_restart   = true
    preemptible         = true # Cost savings for non-critical synthesis
  }

  service_account {
    scopes = ["cloud-platform"]
  }

  metadata = {
    install-nvidia-driver = "True"
    startup-script        = <<-EOT
      #!/bin/bash
      echo "CAF GPU Worker Initializing..."
      # TODO: Pull repo, install Wan 2.2 deps, start poller
    EOT
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Managed Instance Group for GPU Workers
resource "google_compute_region_instance_group_manager" "worker_gpu_mgr" {
  name               = "caf-worker-gpu-mgr"
  base_instance_name = "caf-worker-gpu"
  region             = "us-central1"

  version {
    instance_template = google_compute_instance_template.worker_gpu.id
  }

  target_size = 0 # Managed by autoscaler, start at 0 to save cost
}

# Autoscaling Policy based on CPU (proxy for GPU load or custom metrics)
resource "google_compute_region_autoscaler" "worker_gpu_autoscaler" {
  name   = "caf-worker-gpu-autoscaler"
  region = "us-central1"
  target = google_compute_region_instance_group_manager.worker_gpu_mgr.id

  autoscaling_policy {
    max_replicas    = 5
    min_replicas    = 0
    cooldown_period = 60

    cpu_utilization {
      target = 0.6
    }
  }
}
