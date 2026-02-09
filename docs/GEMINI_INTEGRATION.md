# Gemini Integration

## Confirmed working endpoints
- **Gemini 2.0 Flash Live API** (`gemini-2.0-flash-live-preview-04-09`) — streaming text responses via Vertex AI
- Multimodal: camera frame (JPEG/PNG) + text prompt in a single `send_client_content` call
- Audio (WAV base64) sent alongside images for ambient hazard detection
- Service account authentication via `GOOGLE_APPLICATION_CREDENTIALS` env var
- **Function calling** with 4 tool declarations for autonomous landmark/hazard management
- **Token counting** via `client.aio.models.count_tokens()` for 1M context tracking

## Live API status: **WORKING**

The Live API is fully integrated in `gemini_client.py`:
- `create_live_stream()` opens a persistent `aio.live.connect()` session per agent
- `send_multimodal()` sends structured `Content(role="user", parts=[...])` turns
- Streaming text response collected via `session.receive()` generator
- JSON response parsed, markdown code fences stripped automatically
- Function calls detected via `tool_call` attribute and processed asynchronously

## Function Calling

Four tools are attached to every Gemini Live session via `NAVISOUND_TOOLS`:

| Function | Trigger | Effect |
|---|---|---|
| `record_landmark` | Gemini identifies a notable feature (door, fountain, sign) | Persists to PostgreSQL + Redis + context window |
| `recall_landmark` | User asks "where was the ___?" | Triggers spatial memory search pipeline |
| `report_hazard` | Gemini detects an immediate threat | Saves to DB + publishes via Redis pub/sub |
| `update_route` | Gemini decides to change navigation instructions | Logged to context window for continuity |

Tool responses are sent back via `session.send_tool_response()` so the model can continue generating.

## Architecture per session

Each WebSocket session creates **5 independent Gemini Live connections** (one per agent):
1. SceneAgent — visual scene understanding with bounding boxes
2. HazardAgent — imminent threat detection with temporal tracking
3. AudioFeedbackAgent — spatial audio parameter generation
4. NavigationAgent — turn-by-turn routing with GPS
5. SpatialMemory — queryable landmark recall

All 5 are created in parallel via `asyncio.gather` on connection open and closed on disconnect.

## Spatial Grounding

Agent prompts request bounding box coordinates for every detected object:
```json
"bounding_box": {"ymin": 400, "xmin": 50, "ymax": 800, "xmax": 300}
```
Coordinates are normalised 0-1000 and stored in PostgreSQL's `spatial_landmarks` table.

## Token counting (1M context window)

- `context_manager.py` tracks per-session token usage via `client.aio.models.count_tokens()`
- Maximum: `1,048,576` tokens (Gemini 2.0 Flash)
- Prune target: 90% — oldest observations are dropped when approaching limit
- Landmark entries are never pruned (persistent spatial memory)
- Falls back to character-based estimation (~4 chars/token) if API unavailable

## Latency measurements (from local test runs)
- Text-only query (NavigationAgent): **2-5s**
- Video frame (3 parallel agents): **3-8s**
- E2E through gateway: **4-10s** (includes session init on first message)
- After warm-up (sessions already open): **2-4s**

## Fallback behavior
- **API error**: Return last known good direction/distance from `active_sessions` cache
- **Agent exception**: Replace with empty dict; other agents still return results
- **Complete failure**: Return safe "Stop and wait" instruction
- **DB/Redis failure**: Log warning, continue without persistence

## SDK version and API notes
- google-genai >= 1.62.0
- `types.Part` API:
  - `Part(text=...)` — text prompts
  - `Part(inline_data=Blob(mime_type=..., data=...))` — binary image/audio
- `LiveConnectConfig`:
  - `responseModalities=["TEXT"]` — text-only responses
  - `systemInstruction` — agent-specific system prompt
  - `temperature=0.3` — low creativity for reliable JSON output
  - `maxOutputTokens=500` — keeps responses concise
  - `tools=NAVISOUND_TOOLS` — 4 function declarations


