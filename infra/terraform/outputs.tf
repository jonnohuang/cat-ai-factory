output "assets_bucket_url" {
  value = google_storage_bucket.assets.url
}

output "outputs_bucket_url" {
  value = google_storage_bucket.outputs.url
}

output "runner_service_account_email" {
  value = google_service_account.runner.email
}

output "receiver_service_url" {
  value = google_cloud_run_v2_service.receiver.uri
}

output "orchestrator_service_url" {
  value = google_cloud_run_v2_service.orchestrator.uri
}

output "worker_service_url" {
  value = google_cloud_run_v2_service.worker.uri
}

output "queue_name" {
  value = google_cloud_tasks_queue.orchestrator_queue.name
}
