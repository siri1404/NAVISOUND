import json
import time
from typing import Dict, List, Optional

from gemini_client import GeminiLiveClient


class HazardAgent:
    """Predictive obstacle + safety detection with temporal tracking.

    Maintains a rolling history of hazard detections across frames so
    Gemini can reason about movement vectors (e.g. "person was 10 ft
    away 2 seconds ago, now 5 ft → approaching at ~2.5 ft/s").
    """

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client
        # Per-session temporal history: list of {timestamp, hazards, frame_index}
        self._history: Dict[str, List[dict]] = {}
        self._frame_counter: Dict[str, int] = {}

    def _get_temporal_context(self, session_id: str, last_n: int = 5) -> str:
        """Build a temporal context string from the last N hazard frames."""
        history = self._history.get(session_id, [])
        if not history:
            return "No previous hazard history."

        parts: List[str] = []
        for entry in history[-last_n:]:
            elapsed_ms = int((time.time() - entry["timestamp"]) * 1000)
            parts.append(
                f"[{elapsed_ms}ms ago, frame #{entry['frame_index']}] "
                f"{json.dumps(entry['hazards'], default=str)[:300]}"
            )
        return "\n".join(parts)

    async def detect_hazards(
        self, session_id: str, image_b64: str, audio_b64: str | None = None
    ) -> dict:
        frame_idx = self._frame_counter.get(session_id, 0)
        temporal_ctx = self._get_temporal_context(session_id)

        prompt = (
            f"Frame #{frame_idx} — Identify ALL threats within 15 feet.\n\n"
            "TEMPORAL HISTORY (use this to detect MOVEMENT and PREDICT trajectories):\n"
            f"{temporal_ctx}\n\n"
            "Compare current positions to previous frames. If an object was farther "
            "away before and is now closer, it is APPROACHING — calculate speed.\n"
            "If a hazard is moving toward the user, increase urgency.\n\n"
            "For each hazard include bounding_box [ymin, xmin, ymax, xmax] "
            "in normalised 0-1000 coordinates.\n\n"
            "OUTPUT:\n"
            "{\n"
            '  "imminent_hazards": [\n'
            '    {"type": "person-approaching", "direction": "left", '
            '"distance_feet": 5, "speed_ft_per_sec": 2.5, '
            '"urgency": "CRITICAL", '
            '"bounding_box": {"ymin": 200, "xmin": 50, "ymax": 800, "xmax": 350}}\n'
            "  ],\n"
            '  "predicted_hazards": [\n'
            '    {"type": "stairs", "distance_feet": 8, '
            '"warning_lead_time_sec": 3, "trajectory": "user-approaching"}\n'
            "  ],\n"
            '  "safe_status": true,\n'
            '  "recommended_action": "Continue forward, be alert to left"\n'
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            image_b64=image_b64,
            audio_b64=audio_b64,
            text=prompt,
            image_mime="image/jpeg",
        )

        # Store in temporal history for next frame's comparison
        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append({
            "timestamp": time.time(),
            "frame_index": frame_idx,
            "hazards": response.get("imminent_hazards", []),
        })
        # Keep only last 30 frames of history
        if len(self._history[session_id]) > 30:
            self._history[session_id] = self._history[session_id][-30:]

        self._frame_counter[session_id] = frame_idx + 1

        return response

    def clear_session(self, session_id: str) -> None:
        """Clean up session-specific state."""
        self._history.pop(session_id, None)
        self._frame_counter.pop(session_id, None)
