from gemini_client import GeminiLiveClient


class AudioFeedbackAgent:
    """Generates audio guidance parameters from navigation context."""

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client

    async def generate_audio_params(self, session_id: str, context: dict) -> dict:
        prompt = (
            "Generate audio guidance parameters for spatial navigation.\n"
            "Use the following context and output JSON only:\n"
            f"Context: {context}\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            "  \"pan\": -1.0 to 1.0,\n"
            "  \"volume\": 0.0 to 1.0,\n"
            "  \"tone_hz\": 200 to 1200,\n"
            "  \"cadence_bpm\": 40 to 160,\n"
            "  \"voice_instruction\": \"Short guidance sentence\"\n"
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            text=prompt,
        )
        return response
