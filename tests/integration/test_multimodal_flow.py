"""Integration test: send an image + text query through the full pipeline."""

import asyncio
import base64
import io
import json
import time
import uuid

import pytest
import websockets
from PIL import Image


def generate_test_frame() -> str:
    """Create a synthetic JPEG test image."""
    img = Image.new("RGB", (640, 480), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.mark.asyncio
async def test_multimodal_video_then_text():
    """Sends a video_frame, then a text_query, and asserts both return valid JSON."""
    session_id = str(uuid.uuid4())
    uri = "ws://localhost:8000/agent/stream"

    async with websockets.connect(
        uri,
        additional_headers={"X-Session-Id": session_id},
        open_timeout=15,
    ) as ws:
        # 1) Send video frame
        frame_b64 = generate_test_frame()
        await ws.send(json.dumps({
            "type": "video_frame",
            "data": frame_b64,
            "timestamp": time.time(),
        }))

        video_resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        assert "navigation" in video_resp, f"Missing navigation key: {video_resp}"
        assert "hazards" in video_resp, f"Missing hazards key: {video_resp}"
        assert "audio" in video_resp, f"Missing audio key: {video_resp}"
        print(f"video_frame response: {json.dumps(video_resp, indent=2)}")

        # 2) Send text query
        await ws.send(json.dumps({
            "type": "text_query",
            "destination": "nearest door",
            "timestamp": time.time(),
        }))

        text_resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        # NavigationAgent should return routing fields
        assert isinstance(text_resp, dict), f"Expected dict: {text_resp}"
        print(f"text_query response: {json.dumps(text_resp, indent=2)}")


@pytest.mark.asyncio
async def test_multimodal_audio_chunk():
    """Sends a fake audio chunk and expects hazard analysis back."""
    session_id = str(uuid.uuid4())
    uri = "ws://localhost:8000/agent/stream"

    async with websockets.connect(
        uri,
        additional_headers={"X-Session-Id": session_id},
        open_timeout=15,
    ) as ws:
        # Fake 16kHz mono WAV (just silence)
        silence = b"\x00" * 4096
        audio_b64 = base64.b64encode(silence).decode()

        await ws.send(json.dumps({
            "type": "audio_chunk",
            "data": audio_b64,
            "image_b64": generate_test_frame(),
            "timestamp": time.time(),
        }))

        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        assert isinstance(resp, dict)
        print(f"audio_chunk response: {json.dumps(resp, indent=2)}")
