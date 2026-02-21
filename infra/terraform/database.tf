resource "google_firestore_database" "database" {
  name        = var.firestore_database_id
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Ensure we don't accidentally delete production data
  deletion_policy = "ABANDON"
}
