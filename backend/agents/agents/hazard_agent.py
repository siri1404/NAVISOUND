from gemini_client import GeminiLiveClient


class HazardAgent:
    """Predictive obstacle + safety detection."""

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client

    async def detect_hazards(
        self, session_id: str, image_b64: str, audio_b64: str | None = None
    ) -> dict:
        prompt = (
            "Identify IMMEDIATE THREATS (next 5 feet):\n"
            "OUTPUT:\n"
            "{\n"
            "  \"imminent_hazards\": [\n"
            "    {\"type\": \"person-approaching\", \"direction\": \"left\", "
            "\"speed\": \"fast\", \"urgency\": \"CRITICAL\"}\n"
            "  ],\n"
            "  \"predicted_hazards\": [\n"
            "    {\"type\": \"stairs\", \"distance_feet\": 8, "
            "\"warning_lead_time_sec\": 3}\n"
            "  ],\n"
            "  \"safe_status\": true,\n"
            "  \"recommended_action\": \"Continue forward, be alert to left\"\n"
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            image_b64=image_b64,
            audio_b64=audio_b64,
            text=prompt,
            image_mime="image/jpeg",
        )
        return response
