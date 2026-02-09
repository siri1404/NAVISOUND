# NaviSound

Real-time spatial audio navigation system for blind and low-vision users.  
Uses Gemini 2.0 Flash Live API for multimodal scene understanding, hazard detection, and turn-by-turn routing — all streamed over WebSockets with sub-second latency.

## Architecture

```
Browser (React + Web Audio)  ─ws─▸  Express Gateway (:3000)
                                         │
                                    ws relay
                                         │
                              FastAPI Orchestrator (:8000)
                              ┌──────────┼──────────┐
                          SceneAgent  HazardAgent  AudioAgent
                              └──────────┼──────────┘
                                   Gemini 2.0 Flash
                                   (Vertex AI Live API)
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- GCP service account key (`config/gcp-key.json`)

### 1. Backend (FastAPI)
```bash
cd backend/agents
pip install -r requirements.txt

export GOOGLE_APPLICATION_CREDENTIALS=../../config/gcp-key.json
export GCP_PROJECT_ID=navisound
export GCP_REGION=us-central1
export GEMINI_MODEL=gemini-2.0-flash-live-preview-04-09

uvicorn orchestrator:app --host 0.0.0.0 --port 8000
```

### 2. Gateway (Express)
```bash
cd backend/gateway
npm install
node server.js          # listens on :3000
```

### 3. Tests
```bash
# Unit tests (mocked, no Gemini needed)
pytest tests/unit/ -v

# Integration tests (requires running servers + Gemini)
python tests/test_parallel_agents.py
python tests/test_gateway_video.py
```

## Environment Variables

See [config/env.example](config/env.example) for the full list.

## Project Structure

| Path | Description |
|------|-------------|
| `backend/agents/` | Gemini client, 4 agents, FastAPI orchestrator |
| `backend/gateway/` | Express WebSocket relay (browser ↔ FastAPI) |
| `backend/database/` | PostgreSQL/PostGIS schema and ORM models |
| `frontend/` | React UI, SpatialAudioEngine, MediaStreamCapture |
| `tests/` | Unit (mocked) + integration (live Gemini) tests |
| `config/` | Docker, env, GCP service account |
| `docs/` | Architecture, accessibility, testing protocol |

## License

MIT
