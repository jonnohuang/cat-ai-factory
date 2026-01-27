# Terraform (GCP Deployment Notes)

This folder is intended to provision the cloud backbone for Cat AI Factory in a production-style way.

## Goal

Provision minimal, secure, event-driven infrastructure:

- Cloud Run (orchestrator service)
- Pub/Sub topics (daily-jobs, render-jobs)
- Cloud Scheduler (daily trigger)
- GCS bucket (job + output artifacts)
- Firestore (job state tracking)
- Secret Manager (LLM keys)
- Service accounts + least-privilege IAM

## Recommended Service Accounts

1) sa-orchestrator (Cloud Run)
- Secret Manager: access specific secrets
- GCS: write jobs/artifacts
- Pub/Sub: publish render requests
- Firestore: write job status

2) sa-worker (optional: Cloud Run Job / VM / local ADC)
- GCS: read jobs/assets and write outputs
- Firestore: update status (optional)

## Artifact Layout (GCS)

gs://<PROJECT>-cat-ai-factory/
  jobs/YYYY-MM-DD/job.json
  output/YYYY-MM-DD/final.mp4
  output/YYYY-MM-DD/captions.srt
  packs/YYYY-MM-DD/<platform>/{title.txt,description.txt,hashtags.txt}

## Firestore Layout

Collection: jobs
Document: YYYY-MM-DD
Fields:
- status: PLANNED | RENDERED | PACKAGED | PUBLISHED
- job_gcs_uri
- output_gcs_uri
- created_at
- errors (optional)

## Security Notes

- Store all API keys in Secret Manager (never in images, never in git)
- Use least privilege IAM bindings
- Prefer authenticated Pub/Sub triggers
- Keep Cloud Run private where possible (authenticated invocations)

## State Management

IMPORTANT: Terraform state must never be committed.

Ensure .gitignore includes:
- terraform.tfstate
- terraform.tfstate.*
- .terraform/

