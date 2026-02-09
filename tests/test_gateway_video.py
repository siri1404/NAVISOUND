"""Test gateway E2E with video_frame through all parallel agents."""

import asyncio
import base64
import json
import os
import time

import pytest
import websockets


@pytest.mark.asyncio
async def test_gateway_video():
    print("=" * 60)
    print("GATEWAY VIDEO_FRAME: All 3 agents via gateway")
    print("=" * 60)

    img_path = os.path.join(
        os.path.dirname(__file__), os.pardir, "backend", "agents", "test_image.png"
    )
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    print(f"Image loaded: {len(img_b64)} chars")

    async with websockets.connect("ws://localhost:3000", open_timeout=10) as ws:
        print("[1] Connected to gateway")
        await asyncio.sleep(6)  # wait for 4 Gemini sessions to init
        payload = {
            "type": "video_frame",
            "data": img_b64,
            "timestamp": time.time(),
        }
        t0 = time.time()
        await ws.send(json.dumps(payload))
        print("[2] Sent video_frame, waiting...")
        resp = await asyncio.wait_for(ws.recv(), timeout=60)
        lat = time.time() - t0
        resp_data = json.loads(resp)
        print(f"[3] Response in {lat:.3f}s:")
        print(json.dumps(resp_data, indent=2))
        print()
        nav_ok = "navigation" in resp_data
        haz_ok = "hazards" in resp_data
        aud_ok = "audio" in resp_data
        print(f"navigation: {'YES' if nav_ok else 'MISSING'}")
        print(f"hazards:    {'YES' if haz_ok else 'MISSING'}")
        print(f"audio:      {'YES' if aud_ok else 'MISSING'}")
        print(f"confidence: {resp_data.get('confidence', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(test_gateway_video())
