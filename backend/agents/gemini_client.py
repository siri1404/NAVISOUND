from __future__ import annotations

import base64
import json
import logging
import os
from typing import Dict, Optional

import google.genai as genai
from google.genai import errors

logger = logging.getLogger("navisound.gemini_client")


class GeminiLiveClient:
    """Manages Gemini Live API sessions using the google-genai SDK (v1.62+).

    Uses Vertex AI with service-account credentials pointed to by
    GOOGLE_APPLICATION_CREDENTIALS.
    """

    SYSTEM_PROMPT = (
        "You are NaviSound, a spatial audio navigation AI for blind users.\n"
        "Your job:\n"
        "1. Analyze real-time camera feed + audio + voice commands\n"
        "2. Maintain a persistent mental map using all previous observations\n"
        "3. Provide JSON-structured directions with exact distances and obstacles\n"
        "4. Predict hazards before user encounters them\n\n"
        "ALWAYS RESPOND IN VALID JSON FORMAT. "
        "Follow the exact JSON schema given in each user message."
    )

    def __init__(self, model: Optional[str] = None, region: Optional[str] = None) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash-live-preview-04-09")
        self.region = region or os.getenv("GCP_REGION", "us-central1")
        self.project = os.getenv("GCP_PROJECT_ID", "navisound")

        self._client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.region,
        )

        # session_id -> AsyncSession (the context-manager handle)
        self.sessions: Dict[str, genai.live.AsyncSession] = {}
        # Keep context manager references so we can close properly
        self._session_cms: Dict[str, object] = {}

    async def create_live_stream(self, session_id: str) -> genai.live.AsyncSession:
        config = genai.types.LiveConnectConfig(
            responseModalities=["TEXT"],
            systemInstruction=self.SYSTEM_PROMPT,
            temperature=0.3,
            maxOutputTokens=500,
        )

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

        # Collect response text across chunks
        full_text = ""
        async for msg in session.receive():
            sc = getattr(msg, "server_content", None)
            if sc is None:
                # Could be a tool call or setup message; skip
                continue
            mt = getattr(sc, "model_turn", None)
            if mt and mt.parts:
                for part in mt.parts:
                    if hasattr(part, "text") and part.text:
                        full_text += part.text
            if getattr(sc, "turn_complete", False):
                break

        if not full_text:
            logger.warning("Empty text response for session %s. Returning empty dict.", session_id)
            return {}

        # Strip markdown code fences if present
        cleaned = full_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # remove first and last lines (``` markers)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(
                "Non-JSON response for session %s: %.200s", session_id, cleaned
            )
            return {}

    async def close_session(self, session_id: str) -> None:
        cm = self._session_cms.pop(session_id, None)
        if cm is not None:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self.sessions.pop(session_id, None)


__all__ = ["GeminiLiveClient", "errors"]
