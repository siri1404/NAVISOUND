from __future__ import annotations

import base64
import json
import logging
import os
from typing import Dict, List, Optional

import google.genai as genai
from google.genai import errors

logger = logging.getLogger("navisound.gemini_client")


# ---------------------------------------------------------------------------
#  Function-calling tool definitions
# ---------------------------------------------------------------------------

NAVISOUND_TOOLS = [
    genai.types.Tool(function_declarations=[
        genai.types.FunctionDeclaration(
            name="record_landmark",
            description=(
                "Store a notable landmark or spatial feature the user might "
                "want to recall later (e.g. water fountain, restroom, exit sign)."
            ),
            parameters=genai.types.Schema(
                type="OBJECT",
                properties={
                    "label": genai.types.Schema(
                        type="STRING",
                        description="Short name of the landmark (e.g. 'water fountain')",
                    ),
                    "description": genai.types.Schema(
                        type="STRING",
                        description="Detailed description of the landmark and surroundings",
                    ),
                    "direction": genai.types.Schema(
                        type="STRING",
                        description="Direction from user: left, right, forward, forward-left, etc.",
                    ),
                    "distance_feet": genai.types.Schema(
                        type="NUMBER",
                        description="Estimated distance in feet",
                    ),
                },
                required=["label"],
            ),
        ),
        genai.types.FunctionDeclaration(
            name="recall_landmark",
            description=(
                "Search memory for a previously seen landmark or feature. "
                "Use when the user asks 'where was the ___?'"
            ),
            parameters=genai.types.Schema(
                type="OBJECT",
                properties={
                    "query": genai.types.Schema(
                        type="STRING",
                        description="What the user is looking for",
                    ),
                },
                required=["query"],
            ),
        ),
        genai.types.FunctionDeclaration(
            name="report_hazard",
            description="Report a detected hazard that requires immediate attention.",
            parameters=genai.types.Schema(
                type="OBJECT",
                properties={
                    "hazard_type": genai.types.Schema(
                        type="STRING",
                        description="Type of hazard: stairs, vehicle, person-approaching, wet-floor, drop-off, etc.",
                    ),
                    "urgency": genai.types.Schema(
                        type="STRING",
                        description="CRITICAL, HIGH, MEDIUM, or LOW",
                    ),
                    "direction": genai.types.Schema(
                        type="STRING",
                        description="Direction of hazard from user",
                    ),
                    "distance_feet": genai.types.Schema(
                        type="NUMBER",
                        description="Distance in feet",
                    ),
                    "recommended_action": genai.types.Schema(
                        type="STRING",
                        description="What the user should do",
                    ),
                },
                required=["hazard_type", "urgency"],
            ),
        ),
        genai.types.FunctionDeclaration(
            name="update_route",
            description="Update the navigation route with new step-by-step directions.",
            parameters=genai.types.Schema(
                type="OBJECT",
                properties={
                    "next_direction": genai.types.Schema(
                        type="STRING",
                        description="forward, left, right, forward-left, etc.",
                    ),
                    "distance_feet": genai.types.Schema(
                        type="NUMBER",
                        description="Distance to next waypoint",
                    ),
                    "instruction": genai.types.Schema(
                        type="STRING",
                        description="Spoken instruction for the user",
                    ),
                },
                required=["next_direction", "instruction"],
            ),
        ),
    ]),
]


class GeminiLiveClient:
    """Manages Gemini Live API sessions using the google-genai SDK (v1.62+).

    Uses Vertex AI with service-account credentials pointed to by
    GOOGLE_APPLICATION_CREDENTIALS.

    Features:
     - Function calling (record_landmark, recall_landmark, report_hazard, update_route)
     - 1 M token context window management via session persistence
     - Multimodal input (image + audio + text)
    """

    SYSTEM_PROMPT = (
        "You are NaviSound, a spatial audio navigation AI for blind users.\n"
        "Your job:\n"
        "1. Analyze real-time camera feed + audio + voice commands\n"
        "2. Maintain a persistent mental map using all previous observations\n"
        "3. Provide JSON-structured directions with exact distances and obstacles\n"
        "4. Predict hazards before user encounters them\n"
        "5. Identify and remember landmarks (doors, signs, fountains, restrooms) "
        "using the record_landmark function so users can ask about them later\n"
        "6. When detecting spatial features, include bounding_box with "
        "[ymin, xmin, ymax, xmax] normalised 0-1000 coordinates\n\n"
        "ALWAYS RESPOND IN VALID JSON FORMAT. "
        "Follow the exact JSON schema given in each user message.\n"
        "Use function calls when appropriate to store or recall landmarks."
    )

    def __init__(
        self,
        model: Optional[str] = None,
        region: Optional[str] = None,
        enable_function_calling: bool = True,
        response_modalities: Optional[List[str]] = None,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash-live-preview-04-09")
        self.region = region or os.getenv("GCP_REGION", "us-central1")
        self.project = os.getenv("GCP_PROJECT_ID", "navisound")
        self.enable_function_calling = enable_function_calling
        # Supported: ["TEXT"], ["AUDIO"], or ["TEXT", "AUDIO"]
        # Native audio generation lets Gemini produce spatial audio cues directly
        self.response_modalities = response_modalities or ["TEXT"]

        self._client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.region,
        )

        # session_id -> AsyncSession (the context-manager handle)
        self.sessions: Dict[str, genai.live.AsyncSession] = {}
        # Keep context manager references so we can close properly
        self._session_cms: Dict[str, object] = {}
        # Pending function calls that the orchestrator must resolve
        self.pending_tool_calls: Dict[str, list] = {}

    async def create_live_stream(self, session_id: str) -> genai.live.AsyncSession:
        config = genai.types.LiveConnectConfig(
            responseModalities=self.response_modalities,
            systemInstruction=self.SYSTEM_PROMPT,
            temperature=0.3,
            maxOutputTokens=500,
        )

        # Attach function-calling tools when enabled
        if self.enable_function_calling:
            config.tools = NAVISOUND_TOOLS

        cm = self._client.aio.live.connect(model=self.model, config=config)
        session = await cm.__aenter__()
        self._session_cms[session_id] = cm
        self.sessions[session_id] = session
        return session

    async def send_multimodal(
        self,
        session_id: str,
        image_b64: Optional[str] = None,
        audio_b64: Optional[str] = None,
        text: Optional[str] = None,
        image_mime: str = "image/png",
    ) -> dict:
        if session_id not in self.sessions:
            raise RuntimeError(f"Session not found: {session_id}")

        session = self.sessions[session_id]
        content_parts: list = []

        if text:
            content_parts.append(genai.types.Part(text=text))
        if image_b64:
            content_parts.append(
                genai.types.Part(
                    inline_data=genai.types.Blob(
                        mime_type=image_mime,
                        data=base64.b64decode(image_b64),
                    )
                )
            )
        if audio_b64:
            content_parts.append(
                genai.types.Part(
                    inline_data=genai.types.Blob(
                        mime_type="audio/wav",
                        data=base64.b64decode(audio_b64),
                    )
                )
            )

        # Send via send_client_content (structured turns)
        await session.send_client_content(
            turns=[genai.types.Content(role="user", parts=content_parts)],
            turn_complete=True,
        )

        # Collect response text, audio, and function calls across chunks
        full_text = ""
        audio_chunks: List[bytes] = []
        tool_calls: List[dict] = []

        async for msg in session.receive():
            # Handle tool-call responses from Gemini
            tc = getattr(msg, "tool_call", None)
            if tc and hasattr(tc, "function_calls"):
                for fc in tc.function_calls:
                    call_data = {
                        "id": getattr(fc, "id", ""),
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                    }
                    tool_calls.append(call_data)
                    logger.info("Function call: %s(%s)", fc.name, call_data["args"])
                # After receiving tool calls, send empty tool responses so
                # the model can continue generating text
                tool_responses = []
                for tc_item in tool_calls:
                    tool_responses.append(
                        genai.types.FunctionResponse(
                            name=tc_item["name"],
                            response={"status": "acknowledged", "stored": True},
                        )
                    )
                await session.send_tool_response(function_responses=tool_responses)
                continue

            sc = getattr(msg, "server_content", None)
            if sc is None:
                continue
            mt = getattr(sc, "model_turn", None)
            if mt and mt.parts:
                for part in mt.parts:
                    if hasattr(part, "text") and part.text:
                        full_text += part.text
                    # Native audio output from Gemini (when responseModalities includes AUDIO)
                    if hasattr(part, "inline_data") and part.inline_data:
                        audio_chunks.append(part.inline_data.data)
            if getattr(sc, "turn_complete", False):
                break

        if not full_text and not tool_calls and not audio_chunks:
            logger.warning("Empty response for session %s. Returning empty dict.", session_id)
            return {}

        # Store pending tool calls so orchestrator can process them
        if tool_calls:
            self.pending_tool_calls[session_id] = tool_calls

        # Strip markdown code fences if present
        cleaned = full_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        result: dict = {}
        if cleaned:
            try:
                result = json.loads(cleaned)
            except json.JSONDecodeError:
                logger.warning(
                    "Non-JSON response for session %s: %.200s", session_id, cleaned
                )
                result = {"raw_text": cleaned}

        # Merge function call data into the result
        if tool_calls:
            result["_function_calls"] = tool_calls

        # Include native Gemini-generated audio (base64-encoded PCM)
        if audio_chunks:
            combined = b"".join(audio_chunks)
            result["_native_audio_b64"] = base64.b64encode(combined).decode("ascii")
            result["_native_audio_mime"] = "audio/pcm"  # 24kHz 16-bit mono
            logger.info(
                "Native audio generated for session %s: %d bytes",
                session_id, len(combined),
            )

        return result

    def pop_tool_calls(self, session_id: str) -> List[dict]:
        """Retrieve and clear pending function calls for a session."""
        return self.pending_tool_calls.pop(session_id, [])

    async def close_session(self, session_id: str) -> None:
        cm = self._session_cms.pop(session_id, None)
        if cm is not None:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self.sessions.pop(session_id, None)


__all__ = ["GeminiLiveClient", "errors"]
