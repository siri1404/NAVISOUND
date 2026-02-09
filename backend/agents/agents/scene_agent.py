import json
from typing import List, Optional

from gemini_client import GeminiLiveClient


class SceneAgent:
    """Analyzes visual input with spatial grounding and bounding boxes.

    Each detected object includes normalised bounding-box coordinates
    [ymin, xmin, ymax, xmax] in 0-1000 range, enabling downstream
    spatial reasoning and PostGIS persistence.
    """

    def __init__(self, gemini_client: GeminiLiveClient) -> None:
        self.gemini = gemini_client
        self.context_buffer: List[dict] = []
        self.frame_index: int = 0

    async def analyze_frame(
        self,
        session_id: str,
        image_b64: str,
        context_summary: str = "",
        sensor_data: Optional[dict] = None,
    ) -> dict:
        # Build context from previous frames + sensor data
        context_parts: List[str] = []
        if context_summary:
            context_parts.append(f"CONTEXT:\n{context_summary}")
        if sensor_data:
            if sensor_data.get("lat") is not None:
                context_parts.append(
                    f"GPS: {sensor_data['lat']:.6f}, {sensor_data['lon']:.6f}"
                )
            if sensor_data.get("heading") is not None:
                context_parts.append(f"Heading: {sensor_data['heading']}°")
            if sensor_data.get("speed") is not None:
                context_parts.append(f"Speed: {sensor_data['speed']} m/s")

        context_block = "\n".join(context_parts)

        prompt = (
            "Analyze this camera frame for a blind pedestrian navigating.\n"
            f"Frame #{self.frame_index}\n"
            f"{context_block}\n\n"
            "For EVERY detected object/feature, include a bounding_box with "
            "normalised [ymin, xmin, ymax, xmax] coordinates (0-1000 range).\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            '  "obstacles": [\n'
            '    {"name": "chair", "location": "left", "distance_feet": 3, '
            '"height": "ankle", "urgency": "medium", '
            '"bounding_box": {"ymin": 400, "xmin": 50, "ymax": 800, "xmax": 300}}\n'
            "  ],\n"
            '  "clear_path": {"direction": "forward-right", "distance_feet": 10},\n'
            '  "floor_hazards": [\n'
            '    {"type": "cable", "location": "center", "urgency": "high", '
            '"bounding_box": {"ymin": 700, "xmin": 300, "ymax": 750, "xmax": 700}}\n'
            "  ],\n"
            '  "spatial_features": [\n'
            '    {"label": "door frame", "direction": "forward", "distance_feet": 8, '
            '"bounding_box": {"ymin": 100, "xmin": 350, "ymax": 900, "xmax": 650}, '
            '"description": "Open doorway leading to corridor"}\n'
            "  ],\n"
            '  "confidence": 0.92,\n'
            '  "summary": "Safe path 10ft forward with chair to left"\n'
            "}"
        )

        response = await self.gemini.send_multimodal(
            session_id=session_id,
            image_b64=image_b64,
            text=prompt,
            image_mime="image/jpeg",
        )

        # Tag with frame index for temporal tracking
        response["_frame_index"] = self.frame_index
        self.frame_index += 1

        # Maintain rolling context buffer (last 30 frames)
        self.context_buffer.append(response)
        if len(self.context_buffer) > 30:
            self.context_buffer = self.context_buffer[-30:]

        return response
