# n8n Workflow Setup Guide (PR-29)

This document provides instructions on how to set up the n8n workflows for Cat AI Factory Ops.

## Prerequisites
- A running instance of n8n.
- Access to the CAF Ingress service (local or cloud).
- `CLAWDBOT_GATEWAY_TOKEN` configured in both CAF and n8n.

## Import Instructions

### 1. Human Approval Workflow
1. In n8n, create a new workflow.
2. Click the three dots in the top right and select **Import from File**.
3. Select `repo/ops/n8n/human_approval_v1.json`.
4. Update the **CAF Ingress Approve** node:
   - Ensure the URL points to your Ingress service (e.g., `http://localhost:8080/ops/approve/`).
   - Configure the `Authorization` header with your gateway token.

### 2. Manual Publish Workflow
1. In n8n, create another new workflow.
2. Select **Import from File**.
3. Select `repo/ops/n8n/manual_publish_v1.json`.
4. Update the **CAF Ingress Publish** node:
   - Ensure the URL points to your Ingress service (e.g., `http://localhost:8080/ops/publish/`).
   - Configure the `Authorization` header with your gateway token.

## How it Works

1. **Approval**: When a job is ready for review, n8n (or a human) triggers the `Webhook Approval` node with a `job_id`. This sends a request to CAF Ingress, which writes a `control-approve-*.json` file to the inbox.
2. **Publishing**: Once approved, the job can be published. Triggering the `Webhook Publish` node sends a request to CAF Ingress, which writes a `control-publish-*.json` file to the inbox.

> [!NOTE]
> The orchestrator or a downstream watcher should monitor the `sandbox/inbox` for these control artifacts to advance the state of the job.
