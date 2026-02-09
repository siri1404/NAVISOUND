# Gemini Integration

## Confirmed working endpoints
- **Gemini 2.0 Flash Live API** (`gemini-2.0-flash-live-preview-04-09`) — streaming text responses via Vertex AI
- Multimodal: camera frame (JPEG/PNG) + text prompt in a single `send_client_content` call
- Audio (WAV base64) sent alongside images for ambient hazard detection
- Service account authentication via `GOOGLE_APPLICATION_CREDENTIALS` env var

## Live API status: **WORKING**

The Live API is fully integrated in `gemini_client.py`:
- `create_live_stream()` opens a persistent `aio.live.connect()` session per agent
- `send_multimodal()` sends structured `Content(role="user", parts=[...])` turns
- Streaming text response collected via `session.receive()` generator
- JSON response parsed, markdown code fences stripped automatically

## Architecture per session

Each WebSocket session creates **4 independent Gemini Live connections** (one per agent):
1. SceneAgent — visual scene understanding
2. HazardAgent — imminent threat detection
3. AudioFeedbackAgent — spatial audio parameter generation
4. NavigationAgent — turn-by-turn routing

All 4 are created in parallel via `asyncio.gather` on connection open and closed on disconnect.

## Token counting (1M context window)
- Each Live session maintains conversation history within its 1M token context window
- NavigationAgent stores the last 20 journey log entries for routing continuity
- Planned: `client.models.count_tokens()` for tracking token usage per session

## Latency measurements (from local test runs)
- Text-only query (NavigationAgent): **2-5s**
- Video frame (3 parallel agents): **3-8s**
- E2E through gateway: **4-10s** (includes session init on first message)
- After warm-up (sessions already open): **2-4s**

## Fallback behavior
- **API error**: Return last known good direction/distance from `active_sessions` cache
- **Agent exception**: Replace with empty dict; other agents still return results
- **Complete failure**: Return safe "Stop and wait" instruction

## SDK version and API notes
- google-genai >= 1.62.0
- `types.Part` API:
  - `Part(text=...)` — text prompts
  - `Part(inline_data=Blob(mime_type=..., data=...))` — binary image/audio
- `LiveConnectConfig`:
  - `responseModalities=["TEXT"]` — text-only responses (no audio TTS)
  - `systemInstruction` — agent-specific system prompt
  - `temperature=0.3` — low creativity for reliable JSON output
  - `maxOutputTokens=500` — keeps responses concise


