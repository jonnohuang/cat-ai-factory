resource "google_storage_bucket" "assets" {
  name          = var.assets_bucket_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "outputs" {
  name          = var.outputs_bucket_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "dist_artifacts" {
  name          = var.dist_artifacts_bucket_name
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 180 # Retain distribution artifacts longer for archival
    }
    action {
      type = "Delete"
    }
  }
}
