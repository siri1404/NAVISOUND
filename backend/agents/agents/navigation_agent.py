import json
from typing import List

from gemini_client import GeminiLiveClient


class NavigationAgent:
    """Routes user through space using 1M context window."""

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client
        self.journey_log: List[str] = []

    async def route_to_destination(
        self, session_id: str, destination: str, current_scene: dict
    ) -> dict:
        journey_context = "\n".join(
            [f"[{i}] {obs}" for i, obs in enumerate(self.journey_log[-20:])]
        )

        prompt = (
            f"User destination: {destination}\n"
            f"Current scene: {json.dumps(current_scene)}\n"
            f"Journey so far: {journey_context}\n\n"
            "Provide step-by-step routing. FORMAT:\n"
            "{\n"
            "  \"next_direction\": \"forward-left\" or \"right\" or \"back\",\n"
            "  \"distance_feet\": 12,\n"
            "  \"next_milestone\": \"passing through doorway\",\n"
            "  \"turns_remaining\": 2,\n"
            "  \"estimated_time_sec\": 45,\n"
            "  \"confidence\": 0.85\n"
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            text=prompt,
        )

        self.journey_log.append(f"Routed to {destination}: {response}")
        return response
