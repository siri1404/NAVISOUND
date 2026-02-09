# NaviSound Architecture

## Overview

NaviSound is a real-time spatial audio navigation system for blind and low-vision users. It captures camera frames and microphone audio from the user's phone/device, streams them through a WebSocket pipeline, and returns spatialized audio cues and spoken directions within sub-second latency.

## System Layers

```
┌─────────────────────────────────────────┐
│  Browser (React + Web Audio API)        │
│  - MediaStreamCapture (camera + mic)    │
│  - SpatialAudioEngine (HRTF panner)     │
│  - NavigationUI (keyboard accessible)   │
└──────────────┬──────────────────────────┘
               │ WebSocket (ws://localhost:3000)
┌──────────────▼──────────────────────────┐
│  Express Gateway (Node.js :3000)        │
│  - Session ID generation                │
│  - JSON relay + binary audio relay      │
│  - Auth middleware (token-based)         │
└──────────────┬──────────────────────────┘
               │ WebSocket (ws://localhost:8000/agent/stream)
┌──────────────▼──────────────────────────┐
│  FastAPI Orchestrator (:8000)           │
│  - Per-session Gemini Live connections  │
│  - Parallel agent dispatch              │
│  - Fallback on API errors               │
└──────┬───────┬────────┬─────────────────┘
       │       │        │
   ┌───▼──┐ ┌──▼───┐ ┌──▼──────────┐
   │Scene │ │Hazard│ │Audio        │
   │Agent │ │Agent │ │FeedbackAgent│
   └───┬──┘ └──┬───┘ └──┬──────────┘
       │       │        │
   ┌───▼───────▼────────▼─────┐
   │  Gemini 2.0 Flash Live   │
   │  (Vertex AI, 1M context) │
   └──────────────────────────┘
```

## Agent Responsibilities

| Agent | Input | Output | Runs On |
|-------|-------|--------|---------|
| **SceneAgent** | Camera frame (JPEG b64) | Obstacles, clear path, floor hazards, confidence | Every `video_frame` |
| **HazardAgent** | Camera frame + optional audio | Imminent threats, predicted hazards, safe status | Every `video_frame` + `audio_chunk` |
| **AudioFeedbackAgent** | Navigation context | Pan, volume, tone, cadence, voice instruction | Every `video_frame` |
| **NavigationAgent** | Destination + scene context | Step-by-step routing, distance, milestones | `text_query` / `voice_command` |

## Message Flow

1. **video_frame**: SceneAgent + HazardAgent + AudioFeedbackAgent run **in parallel** via `asyncio.gather`
2. **text_query**: NavigationAgent routes to destination
3. **voice_command**: Parsed and dispatched to NavigationAgent
4. **audio_chunk**: Forwarded to HazardAgent for ambient sound analysis

## Fallback Strategy

- If Gemini API errors, the orchestrator returns the last known good direction/distance
- If all agents fail, returns a safe "stop and wait" instruction
- Individual agent exceptions are caught and replaced with empty dicts

## Data Persistence (planned)

- PostgreSQL + PostGIS for session history, scene snapshots, hazard events
- Redis for sub-second scene caching between frames
