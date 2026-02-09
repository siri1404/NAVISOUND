import json
from typing import List

from gemini_client import GeminiLiveClient


class SceneAgent:
    """Analyzes visual input with spatial grounding."""

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client
        self.context_buffer: List[dict] = []

    async def analyze_frame(self, session_id: str, image_b64: str) -> dict:
        prompt = (
            "Analyze this camera frame for a blind pedestrian navigating indoors.\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            "  \"obstacles\": [\n"
            "    {\"name\": \"chair\", \"location\": \"left\", \"distance_feet\": 3, "
            "\"height\": \"ankle\", \"urgency\": \"medium\"},\n"
            "  ],\n"
            "  \"clear_path\": {\"direction\": \"forward-right\", \"distance_feet\": 10},\n"
            "  \"floor_hazards\": [\n"
            "    {\"type\": \"cable\", \"location\": \"center\", \"urgency\": \"high\"}\n"
            "  ],\n"
            "  \"spatial_features\": [\"door frame\", \"wall edge\", \"floor texture change\"],\n"
            "  \"confidence\": 0.92,\n"
            "  \"summary\": \"Safe path 10ft forward with small obstacle to left\"\n"
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            image_b64=image_b64,
            text=prompt,
            image_mime="image/jpeg",
        )

        self.context_buffer.append(response)
        return response
