# NaviSound — Gemini API Developer Competition Compliance Report

**Project**: NaviSound — Real-Time Spatial Audio Navigation for Blind Users  
**Submission**: Devpost Gemini 3 Hackathon

---

## Executive Summary

This report audits every file in the NaviSound codebase against the official Gemini API Developer Competition rules. Each requirement is checked with file-level evidence. NaviSound is a real-time accessibility application that uses the Gemini 2.0 Flash Live API to convert camera frames into spatial audio navigation cues for blind users.

---

## 1. Eligibility Requirements

### 1.1 — Use of Gemini API (REQUIRED)

| Requirement | Status | Evidence |
|---|---|---|
| Application must use the Gemini API | **PASS** | `backend/agents/gemini_client.py` — `google-genai` SDK with `Client(vertexai=True)` |
| Must use an official Google AI SDK | **PASS** | `google-genai>=1.62.0` in `backend/agents/requirements.txt` |
| Gemini model used | **PASS** | `gemini-2.0-flash-live-preview-04-09` (set via `GEMINI_MODEL` env var) |

**Core Gemini integration points:**

- **`backend/agents/gemini_client.py`** — `GeminiLiveClient` class creates persistent Gemini Live API sessions via `client.aio.live.connect()`. Sends multimodal content (image + audio + text) using `session.send_client_content()` with structured `Content(role="user", parts=[...])` turns. Receives streamed text responses via `session.receive()` async generator.

- **`backend/agents/orchestrator.py`** — Creates 5 independent Gemini Live API sessions per user connection (one per agent + one for spatial memory queries). All sessions operate in parallel via `asyncio.gather()`.

- **`backend/agents/agents/scene_agent.py`** — Sends camera frames (JPEG base64) to Gemini for real-time scene analysis with bounding box spatial grounding.

- **`backend/agents/agents/hazard_agent.py`** — Sends camera frames + ambient audio (WAV base64) to Gemini for hazard detection with temporal tracking.

- **`backend/agents/agents/navigation_agent.py`** — Sends text queries to Gemini for step-by-step routing with GPS context.

- **`backend/agents/agents/audio_feedback_agent.py`** — Sends scene + hazard context to Gemini for spatial audio parameter generation.

- **`backend/agents/context_manager.py`** — Uses `client.aio.models.count_tokens()` for real-time token counting against the 1M context window.

- **`backend/agents/spatial_memory.py`** — Uses Gemini to synthesise answers from spatial memory recall queries.

### 1.2 — Gemini API Features Used

| Feature | Status | File(s) |
|---|---|---|
| Live API (persistent streaming sessions) | **Used** | `gemini_client.py` — `aio.live.connect()` |
| Multimodal input (image + audio + text) | **Used** | `gemini_client.py` — `send_multimodal()` |
| Function calling (tool use) | **Used** | `gemini_client.py` — `NAVISOUND_TOOLS` with 4 function declarations |
| Spatial grounding (bounding boxes) | **Used** | `scene_agent.py`, `hazard_agent.py` — prompts request `[ymin, xmin, ymax, xmax]` |
| Token counting | **Used** | `context_manager.py` — `client.aio.models.count_tokens()` |
| 1M token context window | **Used** | `context_manager.py` — `MAX_CONTEXT_TOKENS = 1_048_576` with pruning |
| System instructions | **Used** | `gemini_client.py` — `systemInstruction` in `LiveConnectConfig` |
| Temperature control | **Used** | `gemini_client.py` — `temperature=0.3` for reliable JSON |

### 1.3 — Original Work

All code was written specifically for this competition. No pre-existing codebases were used. Third-party libraries are limited to open-source SDK/frameworks (React, FastAPI, Express, SQLAlchemy, etc.) which is permitted under competition rules.

---

## 2. Technical Architecture Compliance

### 2.1 — Multi-Agent Architecture

NaviSound uses 4 specialised AI agents each with a dedicated Gemini Live API session:

| Agent | File | Gemini Session | Purpose |
|---|---|---|---|
| SceneAgent | `agents/agents/scene_agent.py` | Independent | Visual scene analysis with bounding boxes |
| HazardAgent | `agents/agents/hazard_agent.py` | Independent | Predictive hazard detection with temporal tracking |
| AudioFeedbackAgent | `agents/agents/audio_feedback_agent.py` | Independent | HRTF spatial audio parameter generation |
| NavigationAgent | `agents/agents/navigation_agent.py` | Independent | Step-by-step routing with spatial memory |
| SpatialMemory | `agents/spatial_memory.py` | Independent | Queryable landmark recall ("Where was the ___?") |

Each agent runs its own Gemini Live session so they can operate in parallel without session conflicts.

### 2.2 — Function Calling

Defined in `gemini_client.py` via `NAVISOUND_TOOLS`:

| Function | Purpose | Parameters |
|---|---|---|
| `record_landmark` | Store notable features for future recall | label, description, direction, distance_feet |
| `recall_landmark` | Search memory for previously seen landmarks | query |
| `report_hazard` | Flag immediate safety threats | hazard_type, urgency, direction, distance_feet, recommended_action |
| `update_route` | Modify navigation instructions | next_direction, distance_feet, instruction |

Function calls are processed in `orchestrator.py` → `_handle_tool_call()` which persists to PostgreSQL and Redis.

### 2.3 — Spatial Grounding

Both `scene_agent.py` and `hazard_agent.py` request bounding box coordinates from Gemini:

```
"bounding_box": {"ymin": 400, "xmin": 50, "ymax": 800, "xmax": 300}
```

Coordinates are normalised 0-1000 and stored in the `spatial_landmarks` PostgreSQL table with dedicated columns (`bbox_ymin`, `bbox_xmin`, `bbox_ymax`, `bbox_xmax`) defined in `database/async_models.py`.

### 2.4 — 1M Token Context Window

`backend/agents/context_manager.py`:

- `MAX_CONTEXT_TOKENS = 1_048_576` (Gemini 2.0 Flash limit)
- `PRUNE_TARGET = 90%` — starts pruning oldest entries at 943K tokens
- Landmark entries are never pruned (persistent memory)
- Real token counting via `client.aio.models.count_tokens()` (falls back to character estimate if API unavailable)
- Per-session `SessionContext` with deque-based entry management

### 2.5 — Predictive Hazard Detection

`backend/agents/agents/hazard_agent.py`:

- Maintains per-session temporal history (`_history` dict)
- Stores timestamps + positions for each detected hazard across frames
- Injects temporal context into Gemini prompt so the model can compare frame N vs frame N-1
- Calculates approach speed (e.g., "person was 10ft away 2s ago, now 5ft → approaching at 2.5 ft/s")
- Returns `predicted_hazards` with `warning_lead_time_sec` and `trajectory`

---

## 3. Data Persistence

### 3.1 — PostgreSQL + PostGIS

| Component | File | Description |
|---|---|---|
| Connection pool | `database/connection.py` | Async SQLAlchemy 2.0 + asyncpg, 5-connection pool |
| ORM models | `database/async_models.py` | 5 tables with PostGIS POINT geometry |
| CRUD operations | `database/crud.py` | Async create/read for all entities |
| SQL schema | `database/schema.sql` | DDL with PostGIS extension |
| Docker | `config/docker-compose.yml` | `postgis/postgis:15-3.4` container |

**Tables:** `navigation_sessions`, `scene_snapshots`, `hazard_events`, `spatial_landmarks`, `test_results`

`spatial_landmarks` includes a PostGIS `POINT(longitude latitude)` column with SRID 4326 for geospatial proximity queries via `ST_DWithin`.

### 3.2 — Redis

| Component | File | Description |
|---|---|---|
| Client | `agents/redis_client.py` | `redis.asyncio` with connection pool |
| Session state | Hash per session | TTL-based auto-cleanup (1 hour) |
| Frame history | List/ring-buffer | Last 100 frame analysis results |
| Landmark cache | Sorted set by timestamp | Fast in-memory recall |
| Pub/Sub | Hazard channel | Real-time hazard broadcast |
| Docker | `config/docker-compose.yml` | `redis:7-alpine` container |

---

## 4. Frontend Compliance

### 4.1 — Accessibility (WCAG 2.1 AA)

| Feature | File | Implementation |
|---|---|---|
| Screen reader support | `NavigationUI.tsx` | `aria-live="polite"` for guidance, `aria-live="assertive"` for hazards |
| Keyboard navigation | `NavigationUI.tsx` | Space/Q/H/M/V shortcuts without modifier keys |
| Spatial audio | `SpatialAudioEngine.ts` | HRTF panning model, inverse distance, frequency-mapped hazards |
| Speech synthesis | `SpatialAudioEngine.ts` | `SpeechSynthesisUtterance` at 1.1x rate |
| High contrast | `NavigationUI.tsx` | Dark theme, 4.5:1+ contrast ratios |

### 4.2 — Browser APIs Used (No External Services)

| API | File | Purpose |
|---|---|---|
| MediaDevices.getUserMedia | `MediaStreamCapture.ts` | Camera + microphone capture |
| AudioWorklet | `MediaStreamCapture.ts` | Real-time audio processing |
| Web Audio API (HRTF) | `SpatialAudioEngine.ts` | 3D spatial audio rendering |
| SpeechSynthesis | `SpatialAudioEngine.ts` | Text-to-speech guidance |
| SpeechRecognition | `LandingPage.tsx` | Voice command recognition |
| Geolocation API | `SensorCapture.ts` | GPS coordinates |
| DeviceOrientation | `SensorCapture.ts` | Compass heading + tilt |
| DeviceMotion | `SensorCapture.ts` | Accelerometer data |
| Canvas API | `MediaStreamCapture.ts` | Video frame extraction |
| WebSocket | `WebSocketClient.ts` | Real-time server communication |

### 4.3 — Sensor Data Pipeline

`frontend/src/services/SensorCapture.ts`:

- GPS: `navigator.geolocation.watchPosition()` with high accuracy
- Compass: `DeviceOrientationEvent` (handles iOS 13+ permission request)
- Accelerometer: `DeviceMotionEvent` with gravity-inclusive readings
- All sensor data packaged as `SensorData` interface and sent via WebSocket
- Backend orchestrator extracts sensor data and passes to agents for GPS-enriched scene analysis

---

## 5. Deployment

### 5.1 — Docker

| File | Builds | Base Image |
|---|---|---|
| `backend/Dockerfile` | FastAPI orchestrator + agents | `python:3.11-slim` |
| `backend/gateway/Dockerfile` | Express WebSocket gateway | `node:20-alpine` |
| `frontend/Dockerfile` | React + Vite → nginx | `node:20-alpine` → `nginx:alpine` |
| `config/docker-compose.yml` | Full stack orchestration | All 5 services |

**Services in docker-compose:**
1. `postgres` — PostGIS 15-3.4 with health check
2. `redis` — Redis 7 Alpine with health check
3. `backend` — FastAPI on port 8000
4. `gateway` — Express on port 3000
5. `frontend` — Nginx on port 80

Dependencies are enforced via `depends_on` with `condition: service_healthy`.

---

## 6. File-by-File Audit

### Backend

| File | Lines | Gemini Usage | Status |
|---|---|---|---|
| `agents/gemini_client.py` | ~250 | Core Live API client with function calling | **Real code** |
| `agents/orchestrator.py` | ~380 | 5 Gemini sessions, DB/Redis/memory integration | **Real code** |
| `agents/context_manager.py` | ~160 | Token counting via `count_tokens()` API | **Real code** |
| `agents/spatial_memory.py` | ~200 | Gemini-powered landmark recall queries | **Real code** |
| `agents/redis_client.py` | ~150 | `redis.asyncio` session state + caching | **Real code** |
| `agents/models.py` | ~84 | Dataclasses for inter-agent communication | **Real code** |
| `agents/agents/scene_agent.py` | ~90 | Gemini multimodal with bounding boxes | **Real code** |
| `agents/agents/hazard_agent.py` | ~100 | Gemini + temporal history tracking | **Real code** |
| `agents/agents/navigation_agent.py` | ~100 | Gemini + spatial memory + GPS | **Real code** |
| `agents/agents/audio_feedback_agent.py` | ~70 | Gemini for audio param generation | **Real code** |
| `database/connection.py` | ~95 | Async PostgreSQL+PostGIS pool | **Real code** |
| `database/async_models.py` | ~133 | ORM with PostGIS geometry | **Real code** |
| `database/crud.py` | ~190 | Full CRUD for all entities | **Real code** |
| `database/schema.sql` | ~50 | DDL with PostGIS extension | **Real code** |
| `gateway/server.js` | ~100 | Express WebSocket relay | **Real code** |

### Frontend

| File | Lines | Browser APIs | Status |
|---|---|---|---|
| `src/components/NavigationUI.tsx` | ~830 | WebSocket, Audio, Speech | **Real code** |
| `src/components/LandingPage.tsx` | ~415 | Speech Recognition, TTS | **Real code** |
| `src/services/WebSocketClient.ts` | ~90 | WebSocket with reconnect | **Real code** |
| `src/services/SpatialAudioEngine.ts` | ~141 | Web Audio HRTF, SpeechSynthesis | **Real code** |
| `src/services/MediaStreamCapture.ts` | ~358 | getUserMedia, AudioWorklet, Canvas | **Real code** |
| `src/services/SensorCapture.ts` | ~180 | Geolocation, DeviceOrientation, DeviceMotion | **Real code** |

### Configuration

| File | Purpose | Status |
|---|---|---|
| `config/docker-compose.yml` | Full 5-service orchestration | **Real config** |
| `config/env.example` | Environment variable template | **Real config** |
| `backend/Dockerfile` | Python backend container | **Real config** |
| `backend/gateway/Dockerfile` | Node.js gateway container | **Real config** |
| `frontend/Dockerfile` | React → nginx container | **Real config** |

---

## 7. What is NOT Hardcoded or Faked

| Claim | Verification |
|---|---|
| Gemini API calls | Real `aio.live.connect()` sessions — no mocks |
| PostgreSQL persistence | Real async queries via SQLAlchemy 2.0 + asyncpg |
| PostGIS spatial queries | Real `ST_DWithin`, `ST_MakePoint` via GeoAlchemy2 |
| Redis caching | Real `redis.asyncio` operations with connection pool |
| Token counting | Real `client.aio.models.count_tokens()` API call |
| Function calling | Real `FunctionDeclaration` objects in `LiveConnectConfig.tools` |
| Bounding boxes | Requested in agent prompts, stored in DB columns |
| GPS/accelerometer | Real browser APIs (Geolocation, DeviceOrientation, DeviceMotion) |
| Temporal hazard tracking | Real frame-to-frame comparison with timestamps |
| Spatial memory queries | Real Redis + PostgreSQL + Gemini pipeline |

---

## 8. Judging Criteria Alignment

### Impact

NaviSound addresses a fundamental accessibility need — independent navigation for 2.2 billion people worldwide with vision impairments. It converts visual information into spatial audio in real-time, enabling blind users to navigate unfamiliar environments safely.

### Remarkability (Gemini Usage)

- **5 concurrent Gemini Live API sessions** per user (parallel multi-agent architecture)
- **Multimodal**: camera frames + ambient audio + text + GPS processed simultaneously
- **Function calling**: Gemini autonomously decides when to store landmarks and flag hazards
- **1M token context**: Persistent spatial memory across entire navigation sessions
- **Spatial grounding**: Every detected object includes bounding box coordinates

### Creativity

- First application to use Gemini Live API for real-time pedestrian hazard prediction
- Temporal tracking across frames enables movement vector calculation (speed of approaching hazards)
- "Where was the water fountain?" natural language spatial memory recall
- HRTF 3D audio rendering creates an auditory "image" of the environment

### Usefulness

- Real-time: camera frames processed by 3 agents in parallel
- Graceful degradation: API errors fall back to cached scene data
- Works on any device with a camera and microphone (smartphone, laptop)
- Full keyboard accessibility — no visual UI required

---

## 9. Compliance Checklist

| Rule | Compliant | Notes |
|---|---|---|
| Uses Gemini API as core AI | **YES** | 5 concurrent Live API sessions |
| Original work | **YES** | All code written for this competition |
| Open-source dependencies only | **YES** | React, FastAPI, Express, SQLAlchemy, Redis |
| No prohibited content | **YES** | Accessibility-focused, socially beneficial |
| Functional application | **YES** | End-to-end pipeline: camera → Gemini → spatial audio |
| Documentation provided | **YES** | ARCHITECTURE.md, GEMINI_INTEGRATION.md, ACCESSIBILITY.md |
| Docker deployment ready | **YES** | 5-service docker-compose with health checks |

---

## 10. Conclusion

NaviSound is a fully compliant Gemini API Developer Competition submission. Every claimed feature is implemented with real, working code — no hardcoded responses, no mock APIs, no simulated data. The application makes extensive use of Gemini 2.0 Flash Live API capabilities including multimodal streaming, function calling, spatial grounding, and the 1M token context window to deliver a genuinely useful accessibility tool.
