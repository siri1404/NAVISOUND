# NaviSound Backend — Python 3.11 + FastAPI + Gemini
FROM python:3.11-slim

WORKDIR /app

# System deps for asyncpg, geoalchemy2, and PostGIS GDAL bindings
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libgeos-dev \
        libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Top-level modules (imported directly by orchestrator) ─────────
COPY agents/gemini_client.py .
COPY agents/orchestrator.py .
COPY agents/models.py .
COPY agents/redis_client.py .
COPY agents/context_manager.py .
COPY agents/spatial_memory.py .

# ── Agent sub-package  →  /app/agents/{scene_agent,…}.py ─────────
#    (orchestrator does: from agents.scene_agent import SceneAgent)
COPY agents/agents/ ./agents/

# ── Database package  →  /app/database/ ──────────────────────────
COPY database/ ./database/

# GCP service account key (mounted at runtime via docker-compose)
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/config/gcp-key.json

EXPOSE 8000

CMD ["uvicorn", "orchestrator:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
