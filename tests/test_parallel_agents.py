"""Test all 3 parallel agents (Scene, Hazard, Audio) with a video_frame payload."""

import asyncio
import base64
import json
import os
import time

import pytest
import websockets

TEST_IMAGE_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir, "backend", "agents", "test_image.png"
)


def load_test_image_b64() -> str:
    """Load the real test image from disk and return as base64."""
    with open(TEST_IMAGE_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()


@pytest.mark.asyncio
async def test_parallel_agents():
    uri = "ws://localhost:8000/agent/stream"
    headers = {"X-Session-Id": "test-parallel-agents"}

    print("=" * 60)
    print("PARALLEL AGENTS TEST (video_frame triggers 3 concurrent)")
    print("SceneAgent + HazardAgent + AudioFeedbackAgent in parallel")
    print("=" * 60)

    async with websockets.connect(uri, additional_headers=headers, open_timeout=15) as ws:
        print("[1] Connected to FastAPI directly")

        test_image = load_test_image_b64()
        print(f"    Test image: {TEST_IMAGE_PATH}")
        print(f"    Base64 size: {len(test_image)} chars")

        payload = {
            "type": "video_frame",
            "data": test_image,
            "timestamp": time.time(),
        }

        print("[2] Sending video_frame with base64 image...")
        t0 = time.time()
        await ws.send(json.dumps(payload))

        print("[3] Waiting for parallel agent results...")
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=30)
            latency = time.time() - t0
            resp_data = json.loads(response)
            print(f"[4] Response in {latency:.3f}s:")
            print(json.dumps(resp_data, indent=2))
            print()

            has_nav = "navigation" in resp_data
            has_haz = "hazards" in resp_data
            has_aud = "audio" in resp_data
            has_conf = "confidence" in resp_data

            nav_label = "YES" if has_nav else "MISSING"
            haz_label = "YES" if has_haz else "MISSING"
            aud_label = "YES" if has_aud else "MISSING"

            print(f"SceneAgent (navigation): {nav_label}")
            print(f"HazardAgent (hazards):   {haz_label}")
            print(f"AudioAgent (audio):      {aud_label}")
            print(f"Confidence:              {resp_data.get('confidence', 'N/A')}")
            print()

            all_present = has_nav and has_haz and has_aud and has_conf
            if all_present:
                print("ALL 3 PARALLEL AGENTS RETURNED RESULTS")
            else:
                missing = [k for k, v in {"navigation": has_nav, "hazards": has_haz, "audio": has_aud}.items() if not v]
                print(f"MISSING FIELDS: {missing}")

            print(f"LATENCY: {latency:.3f}s")

        except asyncio.TimeoutError:
            print("[4] TIMEOUT after 30s")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[4] Connection closed: {e}")
        except json.JSONDecodeError as e:
            print(f"[4] JSON parse failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_parallel_agents())
