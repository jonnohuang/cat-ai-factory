resource "google_service_account" "runner" {
  account_id   = "cat-ai-factory-runner"
  display_name = "Cat AI Factory Runner"
}

# Grant Storage Access
resource "google_storage_bucket_iam_member" "assets_viewer" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_storage_bucket_iam_member" "assets_uploader" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_storage_bucket_iam_member" "outputs_admin" {
  bucket = google_storage_bucket.outputs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runner.email}"
}

# Grant Firestore Access
resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

# Grant Cloud Tasks Access
resource "google_project_iam_member" "tasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_project_iam_member" "tasks_viewer" {
  project = var.project_id
  role    = "roles/cloudtasks.viewer"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

# Grant Vertex AI Access
resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runner.email}"
}
