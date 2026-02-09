import json
from typing import Optional

from gemini_client import GeminiLiveClient


class AudioFeedbackAgent:
    """Generates spatial audio guidance parameters from navigation context.

    Produces HRTF panning, volume, tone frequency, and spoken instructions
    that the frontend SpatialAudioEngine renders into 3D audio cues.
    """

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client

    async def generate_audio_params(
        self,
        session_id: str,
        context: dict,
        scene_result: Optional[dict] = None,
        hazard_result: Optional[dict] = None,
    ) -> dict:
        # Build rich context from scene + hazard results
        scene_summary = ""
        if scene_result:
            direction = ""
            cp = scene_result.get("clear_path", {})
            if isinstance(cp, dict):
                direction = cp.get("direction", "")
            scene_summary = (
                f"Clear path: {direction}\n"
                f"Obstacles: {json.dumps(scene_result.get('obstacles', []), default=str)[:300]}\n"
                f"Summary: {scene_result.get('summary', '')}"
            )

        hazard_summary = ""
        if hazard_result:
            hazard_summary = (
                f"Hazards: {json.dumps(hazard_result.get('imminent_hazards', []), default=str)[:300]}\n"
                f"Action: {hazard_result.get('recommended_action', '')}"
            )

        prompt = (
            "Generate spatial audio parameters for real-time navigation.\n"
            f"Scene: {scene_summary}\n"
            f"Hazards: {hazard_summary}\n"
            f"Extra context: {json.dumps(context, default=str)[:200]}\n\n"
            "Rules:\n"
            "- pan: -1.0 (left) to 1.0 (right), matching the safest path direction\n"
            "- volume: 0.0 to 1.0, louder for urgent hazards\n"
            "- tone_hz: 200-1200. Low=safe, High=danger. 800+=critical hazard\n"
            "- cadence_bpm: 40-160. Slow=safe, Fast=danger approaching\n"
            "- voice_instruction: concise spoken sentence for the user\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            '  "pan": 0.3,\n'
            '  "volume": 0.6,\n'
            '  "tone_hz": 400,\n'
            '  "cadence_bpm": 80,\n'
            '  "voice_instruction": "Clear path ahead, slight right"\n'
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            text=prompt,
        )
        return response
