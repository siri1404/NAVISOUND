"""Queryable spatial memory for NaviSound.

Handles "Where was the water fountain?" style queries by combining:
 1. Redis in-memory landmark cache  (fast, current session)
 2. PostgreSQL + PostGIS persistence (durable, cross-session)
 3. Gemini context-window memory     (model-recalled details)
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from context_manager import ContextManager
from redis_client import cache_landmark, recall_landmarks
from gemini_client import GeminiLiveClient

logger = logging.getLogger("navisound.spatial_memory")

# Avoid circular import – CRUD functions are imported lazily
_crud = None


def _get_crud():
    global _crud
    if _crud is None:
        from database import crud as _crud_mod
        _crud = _crud_mod
    return _crud


class SpatialMemory:
    """Dual-store (Redis + Postgres) queryable spatial memory."""

    def __init__(
        self,
        gemini_client: GeminiLiveClient,
        context_manager: ContextManager,
    ) -> None:
        self.gemini = gemini_client
        self.ctx_mgr = context_manager

    # ------------------------------------------------------------------
    #  Write path – store a landmark from scene analysis
    # ------------------------------------------------------------------

    async def record_landmark(
        self,
        session_id: str,
        label: str,
        description: str = "",
        direction: Optional[str] = None,
        distance_feet: Optional[float] = None,
        frame_index: int = 0,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        bbox: Optional[dict] = None,
    ) -> int:
        """Persist a landmark to Postgres and cache it in Redis."""
        crud = _get_crud()

        # 1. Postgres (durable)
        lm_id = await crud.save_landmark(
            session_id=session_id,
            label=label,
            description=description,
            direction=direction,
            distance_feet=distance_feet,
            frame_index=frame_index,
            lat=lat,
            lon=lon,
            bbox=bbox,
        )

        # 2. Redis cache (fast recall)
        await cache_landmark(session_id, label, {
            "id": lm_id,
            "description": description,
            "direction": direction,
            "distance_feet": distance_feet,
            "frame_index": frame_index,
            "lat": lat,
            "lon": lon,
            "bbox": bbox,
        })

        # 3. Context window (model-visible memory)
        ctx_text = f"LANDMARK: {label}"
        if description:
            ctx_text += f" – {description}"
        if direction:
            ctx_text += f" ({direction}"
            if distance_feet:
                ctx_text += f", ~{distance_feet}ft"
            ctx_text += ")"
        await self.ctx_mgr.add_observation(
            session_id, ctx_text, entry_type="landmark"
        )

        logger.info("Recorded landmark '%s' for session %s (id=%d)", label, session_id, lm_id)
        return lm_id

    # ------------------------------------------------------------------
    #  Read path – answer "Where was the ___?" queries
    # ------------------------------------------------------------------

    async def recall(
        self,
        session_id: str,
        query: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> dict:
        """
        Search for a landmark matching *query*.

        Steps:
          1. Fast check in Redis
          2. Full-text search in PostgreSQL
          3. Proximity search if GPS coords available
          4. Ask Gemini to synthesise an answer from context
        """
        matches: List[dict] = []

        # 1. Redis (sub-millisecond)
        redis_results = await recall_landmarks(session_id, query, limit=5)
        for m in redis_results:
            matches.append({"source": "cache", **m})

        # 2. PostgreSQL text search
        crud = _get_crud()
        db_results = await crud.search_landmarks(session_id, query, limit=5)
        for lm in db_results:
            matches.append({
                "source": "database",
                "id": lm.id,
                "label": lm.label,
                "description": lm.description,
                "direction": lm.direction_from_user,
                "distance_feet": lm.distance_feet,
                "frame_index": lm.frame_index,
            })

        # 3. PostGIS proximity search (if we have GPS)
        if lat is not None and lon is not None:
            geo_results = await crud.search_landmarks_near(
                session_id, lat, lon, radius_metres=50.0, limit=5
            )
            for lm in geo_results:
                matches.append({
                    "source": "proximity",
                    "id": lm.id,
                    "label": lm.label,
                    "description": lm.description,
                    "direction": lm.direction_from_user,
                    "distance_feet": lm.distance_feet,
                })

        # 4. Gemini context-window recall
        context_str = self.ctx_mgr.build_context_string(
            session_id, include_landmarks=True
        )

        prompt = (
            f"The user asks: \"{query}\"\n\n"
            f"Memory context:\n{context_str}\n\n"
            f"Database matches: {json.dumps(matches[:10], default=str)}\n\n"
            "Answer the user's question about a previously seen landmark or location. "
            "If a match was found, describe where it was and when it was seen. "
            "If no match, say you haven't encountered it yet.\n\n"
            "OUTPUT JSON:\n"
            "{\n"
            '  "found": true/false,\n'
            '  "label": "water fountain",\n'
            '  "description": "Seen near the main corridor",\n'
            '  "direction": "left",\n'
            '  "distance_feet": 15,\n'
            '  "frame_index": 42,\n'
            '  "voice_response": "The water fountain was on your left about 15 feet back near the main corridor"\n'
            "}"
        )

        gemini_answer = await self.gemini.send_multimodal(
            session_id=session_id,
            text=prompt,
        )

        return {
            "query": query,
            "matches_found": len(matches),
            "database_matches": matches[:10],
            "gemini_answer": gemini_answer,
        }

    # ------------------------------------------------------------------
    #  Bulk extract landmarks from a scene result
    # ------------------------------------------------------------------

    async def extract_and_store_landmarks(
        self,
        session_id: str,
        scene_result: dict,
        frame_index: int = 0,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> List[int]:
        """Parse landmarks from a scene-agent result and store them."""
        ids: List[int] = []

        # spatial_features list
        for feat in scene_result.get("spatial_features", []):
            if isinstance(feat, str):
                lm_id = await self.record_landmark(
                    session_id=session_id,
                    label=feat,
                    frame_index=frame_index,
                    lat=lat,
                    lon=lon,
                )
                ids.append(lm_id)
            elif isinstance(feat, dict):
                bbox = None
                if "bounding_box" in feat:
                    bbox = feat["bounding_box"]
                lm_id = await self.record_landmark(
                    session_id=session_id,
                    label=feat.get("label", feat.get("name", "unknown")),
                    description=feat.get("description", ""),
                    direction=feat.get("direction", feat.get("location", "")),
                    distance_feet=feat.get("distance_feet"),
                    frame_index=frame_index,
                    lat=lat,
                    lon=lon,
                    bbox=bbox,
                )
                ids.append(lm_id)

        # obstacles as landmarks
        for obs in scene_result.get("obstacles", []):
            if isinstance(obs, dict):
                lm_id = await self.record_landmark(
                    session_id=session_id,
                    label=obs.get("name", "obstacle"),
                    description=f"obstacle at {obs.get('location', 'unknown')}",
                    direction=obs.get("location"),
                    distance_feet=obs.get("distance_feet"),
                    frame_index=frame_index,
                    lat=lat,
                    lon=lon,
                    bbox=obs.get("bounding_box"),
                )
                ids.append(lm_id)

        return ids
