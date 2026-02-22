variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "project_number" {
  description = "The GCP project number (numeric)"
  type        = string
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "us-central1"
}

variable "assets_bucket_name" {
  description = "GCS bucket for input media assets"
  type        = string
}

variable "outputs_bucket_name" {
  description = "GCS bucket for final video outputs"
  type        = string
}

variable "dist_artifacts_bucket_name" {
  description = "GCS bucket for derived distribution artifacts"
  type        = string
}

variable "firestore_database_id" {
  description = "The ID of the Firestore database"
  type        = string
  default     = "(default)"
}

variable "queue_id" {
  description = "The ID of the Cloud Tasks queue"
  type        = string
  default     = "caf-orchestrator-queue"
}
