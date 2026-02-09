from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from agents.scene_agent import SceneAgent
from agents.navigation_agent import NavigationAgent
from agents.hazard_agent import HazardAgent
from agents.audio_feedback_agent import AudioFeedbackAgent
from gemini_client import GeminiLiveClient, errors
from context_manager import ContextManager
from spatial_memory import SpatialMemory
import redis_client

# Optional: database. Import fails gracefully if asyncpg not installed.
try:
    from database.connection import init_db, close_db
    from database import crud
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False


logger = logging.getLogger("navisound.orchestrator")
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
#  Application lifespan — initialise & tear down infra connections
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown hook."""
    # --- startup ---
    if DB_AVAILABLE:
        try:
            await init_db()
            logger.info("PostgreSQL + PostGIS ready")
        except Exception as exc:
            logger.warning("DB init failed (running without persistence): %s", exc)

    try:
        await redis_client.init_redis()
        logger.info("Redis ready")
    except Exception as exc:
        logger.warning("Redis init failed (running without cache): %s", exc)

    yield

    # --- shutdown ---
    try:
        await redis_client.close_redis()
    except Exception:
        pass
    if DB_AVAILABLE:
        try:
            await close_db()
        except Exception:
            pass


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"service": "navisound-orchestrator", "status": "ok"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_sessions": len(active_sessions),
        "db_available": DB_AVAILABLE,
    }


# ---------------------------------------------------------------------------
#  Shared infrastructure
# ---------------------------------------------------------------------------

# Context-window manager (token counting + 1 M window)
context_mgr = ContextManager()

# Each agent gets its own GeminiLiveClient so parallel calls don't conflict
scene_client = GeminiLiveClient()
hazard_client = GeminiLiveClient()
# AudioFeedbackAgent can use native Gemini audio generation for spatial cues
# Set via NAVISOUND_AUDIO_MODALITY env var: "TEXT" (default), "AUDIO", or "TEXT,AUDIO"
_audio_modalities = os.getenv("NAVISOUND_AUDIO_MODALITY", "TEXT").split(",")
audio_client = GeminiLiveClient(
    response_modalities=[m.strip() for m in _audio_modalities],
    enable_function_calling=False,  # audio feedback doesn't need tool calls
)
nav_client = GeminiLiveClient()
memory_client = GeminiLiveClient()   # dedicated client for spatial memory queries

scene_agent = SceneAgent(scene_client)
nav_agent = NavigationAgent(nav_client)
hazard_agent = HazardAgent(hazard_client)
audio_agent = AudioFeedbackAgent(audio_client)

# Spatial memory system (Redis + Postgres + Gemini)
spatial_memory = SpatialMemory(memory_client, context_mgr)

ALL_CLIENTS = [scene_client, hazard_client, audio_client, nav_client, memory_client]

active_sessions: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
#  WebSocket endpoint
# ---------------------------------------------------------------------------

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
        "frame_count": 0,
        "hazard_count": 0,
        "sensor_data": {},
    }

    # Persist session in DB
    if DB_AVAILABLE:
        try:
            await crud.create_session(session_id)
        except Exception as exc:
            logger.warning("DB session create failed: %s", exc)

    # Cache session start in Redis
    try:
        await redis_client.set_session_state(session_id, {"status": "active"})
    except Exception:
        pass

    try:
        while True:
            input_data = await websocket.receive_json()

            # Extract & persist sensor data if present
            sensor = input_data.pop("sensor_data", None)
            if sensor:
                active_sessions[session_id]["sensor_data"] = sensor

            result = await orchestrate_with_fallback(session_id, input_data)
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
    finally:
        # Persist final session stats
        sess = active_sessions.get(session_id, {})
        if DB_AVAILABLE:
            try:
                await crud.end_session(
                    session_id,
                    total_frames=sess.get("frame_count", 0),
                    total_hazards=sess.get("hazard_count", 0),
                )
            except Exception:
                pass

        # Cleanup
        await asyncio.gather(*(c.close_session(session_id) for c in ALL_CLIENTS))
        hazard_agent.clear_session(session_id)
        context_mgr.remove_session(session_id)
        try:
            await redis_client.delete_session(session_id)
        except Exception:
            pass
        active_sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
#  Orchestration
# ---------------------------------------------------------------------------

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
    sess = active_sessions.get(session_id, {})
    sensor = sess.get("sensor_data", {})

    # Build context from the context manager
    ctx_string = context_mgr.build_context_string(session_id, max_entries=10)

    if payload_type == "video_frame":
        sess["frame_count"] = sess.get("frame_count", 0) + 1

        # Run 3 agents in parallel with enriched context
        scene_task = scene_agent.analyze_frame(
            session_id, input_data["data"],
            context_summary=ctx_string,
            sensor_data=sensor,
        )
        hazard_task = hazard_agent.detect_hazards(
            session_id, input_data["data"]
        )
        audio_task = audio_agent.generate_audio_params(
            session_id, {"type": "video_frame", "timestamp": input_data.get("timestamp")}
        )

        results = await asyncio.gather(
            scene_task, hazard_task, audio_task, return_exceptions=True
        )

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

        # --- Context-window update (1 M token management) ---
        summary_text = scene_result.get("summary", "")
        if summary_text:
            await context_mgr.add_observation(session_id, summary_text)

        # --- Spatial memory: extract & store landmarks ---
        try:
            await spatial_memory.extract_and_store_landmarks(
                session_id,
                scene_result,
                frame_index=sess.get("frame_count", 0),
                lat=sensor.get("lat"),
                lon=sensor.get("lon"),
            )
        except Exception as exc:
            logger.warning("Landmark storage failed: %s", exc)

        # --- Process function calls from Gemini ---
        for client in [scene_client, hazard_client]:
            tool_calls = client.pop_tool_calls(session_id)
            for tc in tool_calls:
                await _handle_tool_call(session_id, tc, sensor)

        # --- Persist to DB ---
        if DB_AVAILABLE:
            try:
                await crud.save_scene_snapshot(
                    session_id, scene_result,
                    confidence=scene_result.get("confidence", 0),
                )
            except Exception:
                pass

            # Persist hazards
            for h in hazard_result.get("imminent_hazards", []):
                if isinstance(h, dict):
                    sess["hazard_count"] = sess.get("hazard_count", 0) + 1
                    try:
                        await crud.save_hazard_event(
                            session_id,
                            hazard_type=h.get("type", "unknown"),
                            urgency=h.get("urgency", "medium"),
                            direction=h.get("direction"),
                            distance_feet=h.get("distance_feet"),
                        )
                    except Exception:
                        pass

        # --- Cache frame in Redis ---
        try:
            await redis_client.push_frame_result(session_id, {
                "frame": sess.get("frame_count", 0),
                "direction": scene_result.get("clear_path", {}).get("direction", ""),
                "hazards": len(hazard_result.get("imminent_hazards", [])),
            })
        except Exception:
            pass

        # Re-run audio agent with full scene + hazard context for richer guidance
        try:
            audio_result = await audio_agent.generate_audio_params(
                session_id,
                {"type": "video_frame"},
                scene_result=scene_result,
                hazard_result=hazard_result,
            )
        except Exception:
            pass

        # --- Merge into final response ---
        clear_path = scene_result.get("clear_path", {})
        direction = clear_path.get("direction") or scene_result.get("direction", "")
        distance = clear_path.get("distance_feet") or scene_result.get("distance_feet", 0)
        sess["last_clear_direction"] = direction
        sess["last_clear_distance"] = distance

        all_hazards = []
        for h in hazard_result.get("imminent_hazards", hazard_result.get("hazards", [])):
            if isinstance(h, dict):
                all_hazards.append({
                    "type": h.get("type", h.get("name", "obstacle")),
                    "urgency": h.get("urgency", "medium"),
                    "direction": h.get("direction", h.get("location", "")),
                    "distance_feet": h.get("distance_feet"),
                    "speed_ft_per_sec": h.get("speed_ft_per_sec"),
                    "bounding_box": h.get("bounding_box"),
                })
        for obs in scene_result.get("obstacles", []):
            if isinstance(obs, dict):
                all_hazards.append({
                    "type": obs.get("name", obs.get("type", "obstacle")),
                    "urgency": obs.get("urgency", "medium"),
                    "direction": obs.get("location", obs.get("direction", "")),
                    "distance_feet": obs.get("distance_feet"),
                    "bounding_box": obs.get("bounding_box"),
                })
        for fh in scene_result.get("floor_hazards", []):
            if isinstance(fh, dict):
                all_hazards.append({
                    "type": fh.get("type", "floor_hazard"),
                    "urgency": fh.get("urgency", "high"),
                    "direction": fh.get("location", ""),
                    "bounding_box": fh.get("bounding_box"),
                })

        confidence = min(
            scene_result.get("confidence", scene_result.get("confidence_0to1", 0.85)),
            0.95,
        )
        summary = scene_result.get("summary", "") or scene_result.get("long_description", "")
        features = scene_result.get("spatial_features", [])
        hazard_action = hazard_result.get("recommended_action", "")
        predicted = hazard_result.get("predicted_hazards", [])

        ctx_stats = context_mgr.get_stats(session_id)

        response = {
            "direction": direction,
            "distance_feet": distance,
            "hazards": all_hazards,
            "predicted_hazards": predicted,
            "confidence": confidence,
            "audio": audio_result,
            "summary": summary,
            "spatial_features": features,
            "hazard_action": hazard_action,
            "context_stats": ctx_stats,
            "frame_count": sess.get("frame_count", 0),
        }

        # Forward native Gemini-generated audio to frontend if available
        native_audio = audio_result.get("_native_audio_b64")
        if native_audio:
            response["native_audio_b64"] = native_audio
            response["native_audio_mime"] = audio_result.get("_native_audio_mime", "audio/pcm")

        return response

    if payload_type == "text_query":
        ctx_string = context_mgr.build_context_string(session_id, include_landmarks=True)
        return await nav_agent.route_to_destination(
            session_id,
            input_data["destination"],
            input_data.get("current_scene", {}),
            context_summary=ctx_string,
            sensor_data=sensor,
        )

    if payload_type == "voice_command":
        text = input_data.get("text", "")
        # "Where was the ___?" queries → spatial memory recall
        if "where" in text.lower():
            query = text.lower().replace("where was the", "").replace("where is the", "").strip().rstrip("?")
            memory_result = await spatial_memory.recall(
                session_id, query,
                lat=sensor.get("lat"),
                lon=sensor.get("lon"),
            )
            return await nav_agent.handle_memory_query(session_id, query, memory_result)

        # Generic voice route
        return await nav_agent.route_to_destination(
            session_id, text, {},
            context_summary=ctx_string,
            sensor_data=sensor,
        )

    if payload_type == "audio_chunk":
        return await hazard_agent.detect_hazards(
            session_id,
            input_data.get("image_b64", ""),
            input_data.get("data"),
        )

    if payload_type == "memory_query":
        query = input_data.get("query", "")
        memory_result = await spatial_memory.recall(
            session_id, query,
            lat=sensor.get("lat"),
            lon=sensor.get("lon"),
        )
        return await nav_agent.handle_memory_query(session_id, query, memory_result)

    return await nav_agent.route_to_destination(
        session_id,
        input_data.get("destination", ""),
        input_data.get("current_scene", {}),
        context_summary=ctx_string,
        sensor_data=sensor,
    )


# ---------------------------------------------------------------------------
#  Function-call handlers
# ---------------------------------------------------------------------------

async def _handle_tool_call(session_id: str, tool_call: dict, sensor: dict) -> None:
    """Process a function call from Gemini and persist the result."""
    name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    if name == "record_landmark":
        try:
            await spatial_memory.record_landmark(
                session_id=session_id,
                label=args.get("label", "unknown"),
                description=args.get("description", ""),
                direction=args.get("direction"),
                distance_feet=args.get("distance_feet"),
                lat=sensor.get("lat"),
                lon=sensor.get("lon"),
            )
        except Exception as exc:
            logger.warning("record_landmark call failed: %s", exc)

    elif name == "report_hazard":
        if DB_AVAILABLE:
            try:
                await crud.save_hazard_event(
                    session_id,
                    hazard_type=args.get("hazard_type", "unknown"),
                    urgency=args.get("urgency", "medium"),
                    direction=args.get("direction"),
                    distance_feet=args.get("distance_feet"),
                )
            except Exception:
                pass
        # Publish real-time via Redis
        try:
            await redis_client.publish_hazard(session_id, args)
        except Exception:
            pass

    elif name == "recall_landmark":
        # This will be handled as part of the response flow
        logger.info("recall_landmark requested: %s", args.get("query"))

    elif name == "update_route":
        logger.info("update_route: %s", args)
        await context_mgr.add_observation(
            session_id,
            f"ROUTE UPDATE: {args.get('instruction', '')} ({args.get('next_direction', '')})",
            entry_type="route",
        )
