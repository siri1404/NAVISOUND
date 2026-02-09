#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  NaviSound — Google Cloud Run Deployment Script
#
#  Prerequisites:
#    1. gcloud CLI installed & authenticated  (gcloud auth login)
#    2. Docker installed
#    3. A GCP project with billing enabled
#    4. config/gcp-key.json service account key
#
#  Usage:
#    chmod +x deploy/deploy-gcp.sh
#    ./deploy/deploy-gcp.sh
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-navisound}"
REGION="${GCP_REGION:-us-central1}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.0-flash-live-preview-04-09}"
REPO="navisound"
TAG="latest"

BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/backend:${TAG}"
GATEWAY_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/gateway:${TAG}"
FRONTEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/frontend:${TAG}"

echo "══════════════════════════════════════════════════════════════"
echo "  NaviSound — Cloud Run Deployment"
echo "  Project:  ${PROJECT_ID}"
echo "  Region:   ${REGION}"
echo "══════════════════════════════════════════════════════════════"

# ── 1. Enable required APIs ──────────────────────────────────────────
echo "→ Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  aiplatform.googleapis.com \
  --project="${PROJECT_ID}" --quiet

# ── 2. Create Artifact Registry repo (if not exists) ────────────────
echo "→ Creating Artifact Registry repo..."
gcloud artifacts repositories describe "${REPO}" \
  --location="${REGION}" --project="${PROJECT_ID}" 2>/dev/null || \
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --description="NaviSound container images"

# ── 3. Configure Docker auth ────────────────────────────────────────
echo "→ Configuring Docker auth..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ── 4. Build & push images ──────────────────────────────────────────
echo "→ Building backend image..."
docker build -t "${BACKEND_IMAGE}" -f backend/Dockerfile backend/

echo "→ Building gateway image..."
docker build -t "${GATEWAY_IMAGE}" -f backend/gateway/Dockerfile backend/gateway/

echo "→ Building frontend image..."
docker build -t "${FRONTEND_IMAGE}" -f frontend/Dockerfile frontend/

echo "→ Pushing images..."
docker push "${BACKEND_IMAGE}"
docker push "${GATEWAY_IMAGE}"
docker push "${FRONTEND_IMAGE}"

# ── 5. Create Cloud SQL (PostgreSQL + PostGIS) if needed ─────────────
INSTANCE_NAME="navisound-db"
echo "→ Checking Cloud SQL instance..."
if ! gcloud sql instances describe "${INSTANCE_NAME}" --project="${PROJECT_ID}" 2>/dev/null; then
  echo "→ Creating Cloud SQL instance (this takes ~5 min)..."
  gcloud sql instances create "${INSTANCE_NAME}" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --database-flags=cloudsql.enable_postgis=on \
    --root-password=navisound2026

  gcloud sql databases create navisound \
    --instance="${INSTANCE_NAME}" \
    --project="${PROJECT_ID}"
fi

DB_CONNECTION=$(gcloud sql instances describe "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" --format='value(connectionName)')
echo "  DB connection: ${DB_CONNECTION}"

# ── 6. Create Memorystore Redis if needed ────────────────────────────
REDIS_INSTANCE="navisound-redis"
echo "→ Checking Memorystore Redis..."
if ! gcloud redis instances describe "${REDIS_INSTANCE}" \
  --region="${REGION}" --project="${PROJECT_ID}" 2>/dev/null; then
  echo "→ Creating Memorystore Redis (this takes ~3 min)..."
  gcloud redis instances create "${REDIS_INSTANCE}" \
    --size=1 \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --redis-version=redis_7_0
fi

REDIS_HOST=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(host)')
echo "  Redis host: ${REDIS_HOST}"

# ── 7. Create VPC connector (needed for Cloud SQL & Redis) ──────────
CONNECTOR="navisound-vpc"
echo "→ Checking VPC connector..."
gcloud compute networks vpc-access connectors describe "${CONNECTOR}" \
  --region="${REGION}" --project="${PROJECT_ID}" 2>/dev/null || \
gcloud compute networks vpc-access connectors create "${CONNECTOR}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --range="10.8.0.0/28" \
  --min-instances=2 --max-instances=3

# ── 8. Deploy Backend to Cloud Run ──────────────────────────────────
echo "→ Deploying backend..."
gcloud run deploy navisound-backend \
  --image="${BACKEND_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8000 \
  --memory=1Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=10 \
  --timeout=300 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars="GCP_REGION=${REGION}" \
  --set-env-vars="GEMINI_MODEL=${GEMINI_MODEL}" \
  --set-env-vars="POSTGRES_URL=postgresql://postgres:navisound2026@/${PROJECT_ID}?host=/cloudsql/${DB_CONNECTION}" \
  --set-env-vars="REDIS_URL=redis://${REDIS_HOST}:6379" \
  --add-cloudsql-instances="${DB_CONNECTION}" \
  --vpc-connector="${CONNECTOR}" \
  --session-affinity

BACKEND_URL=$(gcloud run services describe navisound-backend \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)')
echo "  Backend URL: ${BACKEND_URL}"

# Convert https to wss for WebSocket
BACKEND_WS_URL=$(echo "${BACKEND_URL}" | sed 's|https://|wss://|')/agent/stream

# ── 9. Deploy Gateway to Cloud Run ──────────────────────────────────
echo "→ Deploying gateway..."
gcloud run deploy navisound-gateway \
  --image="${GATEWAY_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=3000 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --timeout=300 \
  --set-env-vars="FASTAPI_WS_URL=${BACKEND_WS_URL}" \
  --session-affinity

GATEWAY_URL=$(gcloud run services describe navisound-gateway \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)')
echo "  Gateway URL: ${GATEWAY_URL}"

# ── 10. Deploy Frontend to Cloud Run ────────────────────────────────
# For Cloud Run, frontend needs gateway URL at runtime.
# We rebuild the frontend with the gateway URL baked in, or use
# Cloud Run's --set-env-vars with nginx envsubst.
echo "→ Deploying frontend..."
gcloud run deploy navisound-frontend \
  --image="${FRONTEND_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=80 \
  --memory=256Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5

FRONTEND_URL=$(gcloud run services describe navisound-frontend \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)')

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  ✅  NaviSound deployed successfully!"
echo ""
echo "  Frontend:  ${FRONTEND_URL}"
echo "  Gateway:   ${GATEWAY_URL}"
echo "  Backend:   ${BACKEND_URL}"
echo ""
echo "  Cloud SQL: ${DB_CONNECTION}"
echo "  Redis:     ${REDIS_HOST}:6379"
echo "══════════════════════════════════════════════════════════════"
