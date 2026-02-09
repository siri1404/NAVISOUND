from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from agents.scene_agent import SceneAgent
from agents.navigation_agent import NavigationAgent
from agents.hazard_agent import HazardAgent
from agents.audio_feedback_agent import AudioFeedbackAgent
from gemini_client import GeminiLiveClient, errors

app = FastAPI()
logger = logging.getLogger("navisound.orchestrator")
logging.basicConfig(level=logging.INFO)


@app.get("/")
async def root():
    return {"service": "navisound-orchestrator", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "active_sessions": len(active_sessions)}


# Each agent gets its own GeminiLiveClient so parallel calls don't conflict
# on the same Live session.
scene_client = GeminiLiveClient()
hazard_client = GeminiLiveClient()
audio_client = GeminiLiveClient()
nav_client = GeminiLiveClient()

scene_agent = SceneAgent(scene_client)
nav_agent = NavigationAgent(nav_client)
hazard_agent = HazardAgent(hazard_client)
audio_agent = AudioFeedbackAgent(audio_client)

ALL_CLIENTS = [scene_client, hazard_client, audio_client, nav_client]

active_sessions: Dict[str, dict] = {}


@app.websocket("/agent/stream")
async def websocket_agent(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = websocket.headers.get("X-Session-Id")
    if not session_id:
        await websocket.close(code=1008)
        return

    # Create independent Gemini Live sessions for each agent
    await asyncio.gather(*(c.create_live_stream(session_id) for c in ALL_CLIENTS))
    active_sessions[session_id] = {
        "last_clear_direction": None,
        "last_clear_distance": None,
    }

    try:
        while True:
            input_data = await websocket.receive_json()
            result = await orchestrate_with_fallback(session_id, input_data)
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
    finally:
        await asyncio.gather(*(c.close_session(session_id) for c in ALL_CLIENTS))
        active_sessions.pop(session_id, None)


async def orchestrate_with_fallback(session_id: str, input_data: dict) -> dict:
    try:
        result = await orchestrate(session_id, input_data)
        return result

    except errors.APIError as exc:
        logger.warning("Gemini API error: %s. Using fallback for session %s", exc, session_id)
        last_known = active_sessions.get(session_id, {})
        return {
            "mode": "fallback_last_known",
            "direction": last_known.get("last_clear_direction"),
            "distance_feet": last_known.get("last_clear_distance"),
            "warning": "Using cached scene due to connectivity issue",
        }

    except Exception as exc:
        logger.error("Orchestrator error: %s", exc, exc_info=True)
        return {
            "mode": "safe_fallback",
            "instruction": "Stop and wait",
            "reason": "System error detected",
        }


async def orchestrate(session_id: str, input_data: dict) -> dict:
    payload_type = input_data.get("type")

    if payload_type == "video_frame":
        scene_task = scene_agent.analyze_frame(session_id, input_data["data"])
        hazard_task = hazard_agent.detect_hazards(session_id, input_data["data"])
        audio_task = audio_agent.generate_audio_params(
            session_id, {"type": "video_frame", "timestamp": input_data.get("timestamp")}
        )

        results = await asyncio.gather(
            scene_task, hazard_task, audio_task, return_exceptions=True
        )

        # Replace exceptions with empty dicts so one agent failure
        # doesn't crash the whole pipeline
        cleaned = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("Agent %d returned error: %s", i, r)
                cleaned.append({})
            else:
                cleaned.append(r)
        scene_result, hazard_result, audio_result = cleaned

        logger.info("Scene: %s", json.dumps(scene_result, default=str)[:300])
        logger.info("Hazard: %s", json.dumps(hazard_result, default=str)[:300])
        logger.info("Audio: %s", json.dumps(audio_result, default=str)[:300])

        # Handle BOTH nested (clear_path.direction) and flat (direction) formats
        clear_path = scene_result.get("clear_path", {})
        direction = (
            clear_path.get("direction")
            or scene_result.get("direction", "")
        )
        distance = (
            clear_path.get("distance_feet")
            or scene_result.get("distance_feet", 0)
        )
        active_sessions[session_id]["last_clear_direction"] = direction
        active_sessions[session_id]["last_clear_distance"] = distance

        # Merge hazards from all sources (agents may return different formats)
        all_hazards = []
        # Hazard agent: imminent_hazards (nested) or hazards (flat)
        for h in hazard_result.get("imminent_hazards", hazard_result.get("hazards", [])):
            if isinstance(h, dict):
                all_hazards.append({
                    "type": h.get("type", h.get("name", "obstacle")),
                    "urgency": h.get("urgency", "medium"),
                    "direction": h.get("direction", h.get("location", "")),
                    "distance_feet": h.get("distance_feet"),
                })
        # Scene agent: obstacles list
        for obs in scene_result.get("obstacles", []):
            if isinstance(obs, dict):
                all_hazards.append({
                    "type": obs.get("name", obs.get("type", "obstacle")),
                    "urgency": obs.get("urgency", "medium"),
                    "direction": obs.get("location", obs.get("direction", "")),
                    "distance_feet": obs.get("distance_feet"),
                })
        # Scene agent: floor_hazards list
        for fh in scene_result.get("floor_hazards", []):
            if isinstance(fh, dict):
                all_hazards.append({
                    "type": fh.get("type", "floor_hazard"),
                    "urgency": fh.get("urgency", "high"),
                    "direction": fh.get("location", ""),
                })

        # Confidence: nested or flat or _0to1 variant
        confidence = min(
            scene_result.get("confidence",
                scene_result.get("confidence_0to1", 0.85)),
            0.95,
        )

        # Summary: nested or flat or long_description
        summary = (
            scene_result.get("summary", "")
            or scene_result.get("long_description", "")
        )

        # Spatial features
        features = scene_result.get("spatial_features", [])

        # Hazard agent's recommended action as bonus context
        hazard_action = hazard_result.get("recommended_action", "")

        return {
            "direction": direction,
            "distance_feet": distance,
            "hazards": all_hazards,
            "confidence": confidence,
            "audio": audio_result,
            "summary": summary,
            "spatial_features": features,
            "hazard_action": hazard_action,
        }

    if payload_type == "text_query":
        return await nav_agent.route_to_destination(
            session_id,
            input_data["destination"],
            input_data.get("current_scene", {}),
        )

    if payload_type == "voice_command":
        text = input_data.get("text", "")
        if "where" in text.lower():
            return await nav_agent.route_to_destination(
                session_id,
                "recall previous landmark",
                {},
            )

    if payload_type == "audio_chunk":
        return await hazard_agent.detect_hazards(
            session_id,
            input_data.get("image_b64", ""),
            input_data.get("data"),
        )

    return await nav_agent.route_to_destination(
        session_id,
        input_data.get("destination", ""),
        input_data.get("current_scene", {}),
    )
