#!/usr/bin/env bash
# GCP / Vertex AI setup for NaviSound
# Run once per environment to enable required APIs and configure auth.

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-navisound}"
REGION="${GCP_REGION:-us-central1}"
SA_NAME="navisound-service"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="config/gcp-key.json"

echo "=== NaviSound GCP Setup ==="
echo "Project : $PROJECT_ID"
echo "Region  : $REGION"

# Set active project
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "[1/4] Enabling APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com

# Create service account (idempotent)
echo "[2/4] Creating service account..."
gcloud iam service-accounts describe "$SA_EMAIL" &>/dev/null || \
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="NaviSound Service Account"

# Grant Vertex AI User role
echo "[3/4] Granting IAM roles..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user" \
  --condition=None --quiet

# Download key (skip if already exists)
echo "[4/4] Generating key file..."
if [ ! -f "$KEY_FILE" ]; then
  gcloud iam service-accounts keys create "$KEY_FILE" \
    --iam-account="$SA_EMAIL"
  echo "Key saved to $KEY_FILE"
else
  echo "Key file already exists at $KEY_FILE — skipping."
fi

echo ""
echo "Done! Set these env vars before running NaviSound:"
echo "  export GOOGLE_APPLICATION_CREDENTIALS=$KEY_FILE"
echo "  export GCP_PROJECT_ID=$PROJECT_ID"
echo "  export GCP_REGION=$REGION"
