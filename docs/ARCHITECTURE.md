# NaviSound Architecture

## Overview

NaviSound is a real-time spatial audio navigation system for blind and low-vision users. It captures camera frames, microphone audio, and device sensors from the user's phone/device, streams them through a WebSocket pipeline to a multi-agent Gemini 2.0 backend, and returns spatialized 3D audio cues and spoken directions.

## System Layers

```
┌──────────────────────────────────────────────────┐
│  Browser (React + Web Audio API)                 │
│  - MediaStreamCapture (camera + mic @ 10fps)     │
│  - SensorCapture (GPS + compass + accelerometer) │
│  - SpatialAudioEngine (HRTF 3D panner)           │
│  - NavigationUI (keyboard accessible, dark theme) │
└──────────────┬───────────────────────────────────┘
               │ WebSocket (ws://gateway:3000)
┌──────────────▼───────────────────────────────────┐
│  Express Gateway (Node.js :3000)                 │
│  - Session ID generation (crypto.randomUUID)     │
│  - JSON relay + message queuing                  │
│  - Sensor data passthrough                       │
└──────────────┬───────────────────────────────────┘
               │ WebSocket (ws://backend:8000/agent/stream)
┌──────────────▼───────────────────────────────────┐
│  FastAPI Orchestrator (:8000)                    │
│  - 5 per-session Gemini Live connections         │
│  - Parallel agent dispatch (asyncio.gather)      │
│  - Function call processing                      │
│  - Context window management (1M tokens)         │
│  - Fallback on API errors                        │
└──────┬───────┬────────┬──────────┬───────────────┘
       │       │        │          │
   ┌───▼──┐ ┌──▼───┐ ┌──▼────┐ ┌──▼──────────┐
   │Scene │ │Hazard│ │Nav   │ │Audio        │
   │Agent │ │Agent │ │Agent │ │FeedbackAgent│
   └───┬──┘ └──┬───┘ └──┬───┘ └──┬──────────┘
       │       │        │        │
   ┌───▼───────▼────────▼────────▼─────┐
   │  Gemini 2.0 Flash Live API        │
   │  (Vertex AI, 1M context window)   │
   │  Function calling + Spatial ground │
   └───────────────┬───────────────────┘
                   │
   ┌───────────────▼───────────────────┐
   │         Data Layer                │
   │  ┌──────────┐  ┌───────────────┐  │
   │  │PostgreSQL│  │Redis 7        │  │
   │  │+ PostGIS │  │Session cache  │  │
   │  │Landmarks │  │Frame history  │  │
   │  │Hazards   │  │Landmark cache │  │
   │  │Sessions  │  │Pub/Sub hazards│  │
   │  └──────────┘  └───────────────┘  │
   └───────────────────────────────────┘
```

## Agent Responsibilities

| Agent | Input | Output | Runs On |
|-------|-------|--------|---------|
| **SceneAgent** | Camera frame (JPEG b64) + context + GPS | Obstacles with bounding boxes, clear path, floor hazards, spatial features | Every `video_frame` |
| **HazardAgent** | Camera frame + audio + temporal history | Imminent threats with speed vectors, predicted hazards, trajectory analysis | Every `video_frame` + `audio_chunk` |
| **AudioFeedbackAgent** | Scene + hazard results | Pan, volume, tone, cadence, voice instruction for HRTF rendering | Every `video_frame` |
| **NavigationAgent** | Destination + scene + GPS + memory | Step-by-step routing, distance, milestones, memory query responses | `text_query` / `voice_command` / `memory_query` |
| **SpatialMemory** | Scene features + landmarks | Queryable recall: "Where was the water fountain?" | On landmark detection + recall queries |

## Gemini API Features Used

- **Live API**: Persistent streaming sessions via `aio.live.connect()`
- **Multimodal**: Image (JPEG) + Audio (WAV) + Text in single turns
- **Function Calling**: 4 tools (record_landmark, recall_landmark, report_hazard, update_route)
- **Spatial Grounding**: Bounding boxes [ymin, xmin, ymax, xmax] normalised 0-1000
- **Token Counting**: `client.aio.models.count_tokens()` for real-time usage tracking
- **1M Context Window**: Deque-based pruning at 90% utilisation, landmarks never pruned
- **System Instructions**: Agent-specific prompts in `LiveConnectConfig.systemInstruction`

## Message Flow

1. **video_frame**: SceneAgent + HazardAgent + AudioFeedbackAgent run **in parallel** via `asyncio.gather()` → results merged → landmarks extracted → DB/Redis persisted
2. **text_query**: NavigationAgent routes to destination with GPS + memory context
3. **voice_command**: Parsed for "where" queries → SpatialMemory recall; otherwise → NavigationAgent
4. **memory_query**: SpatialMemory searches Redis → PostgreSQL → Gemini context
5. **audio_chunk**: Forwarded to HazardAgent for ambient sound analysis

## Data Persistence

- **PostgreSQL + PostGIS**: Navigation sessions, scene snapshots, hazard events, spatial landmarks with geometry
- **Redis**: Session state (hash), frame history (ring buffer), landmark cache (sorted set), hazard pub/sub
- **Context Manager**: In-memory deque with token accounting, never-pruned landmarks

## Fallback Strategy

- If Gemini API errors → return last known good direction/distance from session cache
- If all agents fail → return safe "stop and wait" instruction  
- Individual agent exceptions are caught and replaced with empty dicts
- DB/Redis failures are logged but don't crash the pipeline

## Deployment

5-service Docker Compose:
1. `postgres` — PostGIS 15-3.4 (health-checked)
2. `redis` — Redis 7 Alpine (health-checked)
3. `backend` — Python 3.11 FastAPI (depends on postgres + redis)
4. `gateway` — Node.js 20 Express (depends on backend)
5. `frontend` — Vite build → nginx (depends on gateway)
