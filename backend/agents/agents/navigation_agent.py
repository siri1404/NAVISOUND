import json
from typing import List, Optional

from gemini_client import GeminiLiveClient


class NavigationAgent:
    """Routes user through space using 1M context window + spatial memory.

    Integrates with the queryable spatial memory system so users can ask
    "Where was the water fountain?" and get real recall from DB + context.
    """

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client
        self.journey_log: List[str] = []

    async def route_to_destination(
        self,
        session_id: str,
        destination: str,
        current_scene: dict,
        context_summary: str = "",
        sensor_data: Optional[dict] = None,
    ) -> dict:
        journey_context = "\n".join(
            [f"[{i}] {obs}" for i, obs in enumerate(self.journey_log[-20:])]
        )

        # Build sensor/GPS context
        sensor_parts: List[str] = []
        if sensor_data:
            if sensor_data.get("lat") is not None:
                sensor_parts.append(
                    f"GPS: {sensor_data['lat']:.6f}, {sensor_data['lon']:.6f}"
                )
            if sensor_data.get("heading") is not None:
                sensor_parts.append(f"Compass heading: {sensor_data['heading']}°")
            if sensor_data.get("speed") is not None:
                sensor_parts.append(f"Walking speed: {sensor_data['speed']} m/s")
        sensor_block = "\n".join(sensor_parts) if sensor_parts else "No GPS data"

        prompt = (
            f"User destination: {destination}\n"
            f"Current scene: {json.dumps(current_scene, default=str)[:500]}\n"
            f"Sensor data: {sensor_block}\n"
            f"Memory context:\n{context_summary[:2000]}\n"
            f"Journey so far:\n{journey_context}\n\n"
            "Provide step-by-step routing. FORMAT:\n"
            "{\n"
            '  "next_direction": "forward-left",\n'
            '  "distance_feet": 12,\n'
            '  "next_milestone": "passing through doorway",\n'
            '  "turns_remaining": 2,\n'
            '  "estimated_time_sec": 45,\n'
            '  "confidence": 0.85,\n'
            '  "voice_instruction": "Walk 12 feet forward-left toward the doorway"\n'
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            text=prompt,
        )

        self.journey_log.append(f"Routed to {destination}: {response}")
        # Keep journey log manageable
        if len(self.journey_log) > 100:
            self.journey_log = self.journey_log[-100:]

        return response

    async def handle_memory_query(
        self,
        session_id: str,
        query: str,
        memory_results: dict,
    ) -> dict:
        """Format a spatial memory recall result into a navigation response."""
        gemini_answer = memory_results.get("gemini_answer", {})
        voice = gemini_answer.get(
            "voice_response",
            f"I don't have information about '{query}' in my memory."
        )
        return {
            "type": "memory_recall",
            "query": query,
            "found": gemini_answer.get("found", False),
            "voice_instruction": voice,
            "details": gemini_answer,
            "database_matches": memory_results.get("database_matches", [])[:5],
        }
