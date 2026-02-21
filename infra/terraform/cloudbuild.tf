resource "google_artifact_registry_repository" "repository" {
  location      = var.region
  repository_id = "cat-ai-factory"
  description   = "Docker repository for Cat AI Factory services"
  format        = "DOCKER"
}

# Cloud Build Service Account Permissions
# (For automated builds and deployments to Cloud Run)

resource "google_project_iam_member" "cloudbuild_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${var.project_number}@cloudbuild.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_iam_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${var.project_number}@cloudbuild.gserviceaccount.com"
}

# Note on Project Number:
# We need the numeric Project Number for the default Cloud Build SA.
# This variable was added to .env and variables.tf.
