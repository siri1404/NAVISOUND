import asyncio
import base64
import io
import time
import uuid
import json

import pytest
import websockets
from PIL import Image


def generate_test_frame() -> str:
    img = Image.new("RGB", (1280, 720), color=(64, 128, 192))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.mark.asyncio
async def test_end_to_end_latency():
    test_frame_b64 = generate_test_frame()
    session_id = str(uuid.uuid4())

    t0 = time.time()
    async with websockets.connect(
        "ws://localhost:8000/agent/stream",
        additional_headers={"X-Session-Id": session_id},
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "video_frame",
                    "data": test_frame_b64,
                    "timestamp": t0,
                }
            )
        )
        await websocket.recv()

    t_total = (time.time() - t0) * 1000

    print(f"Total latency: {t_total}ms")
    # Gemini Live sessions include ~2-4s cold start; 15s is a generous upper bound
    assert t_total < 15000, f"Latency too high: {t_total}ms"

    return t_total
