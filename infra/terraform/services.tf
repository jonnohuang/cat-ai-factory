resource "google_cloud_tasks_queue" "orchestrator_queue" {
  name     = var.queue_id
  location = var.region

  rate_limits {
    max_dispatches_per_second = 10
    max_concurrent_dispatches = 10
  }

  retry_config {
    max_attempts       = 5
    max_retry_duration = "3600s"
    min_backoff        = "10s"
    max_backoff        = "300s"
  }
}

# Placeholder Cloud Run Services
# Note: These require container images in Artifact Registry to be fully functional.

resource "google_cloud_run_v2_service" "receiver" {
  name     = "caf-receiver"
  location = var.region
  
  template {
    service_account = google_service_account.runner.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello" # Placeholder
      env {
        name  = "CAF_INGRESS_MODE"
        value = "cloud"
      }
    }
  }
}

resource "google_cloud_run_v2_service" "orchestrator" {
  name     = "caf-orchestrator"
  location = var.region
  
  template {
    service_account = google_service_account.runner.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello" # Placeholder
      env {
        name  = "CAF_INGRESS_MODE"
        value = "cloud"
      }
    }
  }
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "caf-worker"
  location = var.region
  
  template {
    service_account = google_service_account.runner.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello" # Placeholder
      env {
        name  = "CAF_INGRESS_MODE"
        value = "cloud"
      }
    }
  }
}
