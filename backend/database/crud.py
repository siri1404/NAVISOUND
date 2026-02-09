"""CRUD operations for NaviSound — async PostgreSQL with PostGIS."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from geoalchemy2.functions import ST_DWithin, ST_MakePoint
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.async_models import (
    HazardEvent,
    NavigationSession,
    SceneSnapshot,
    SpatialLandmark,
)
from database.connection import get_session

logger = logging.getLogger("navisound.crud")


# ---------------------------------------------------------------------------
#  Navigation sessions
# ---------------------------------------------------------------------------

async def create_session(session_id: str, user_id: Optional[str] = None) -> None:
    async with get_session() as db:
        db.add(NavigationSession(session_id=session_id, user_id=user_id))


async def end_session(
    session_id: str,
    total_frames: int = 0,
    total_hazards: int = 0,
) -> None:
    async with get_session() as db:
        await db.execute(
            update(NavigationSession)
            .where(NavigationSession.session_id == session_id)
            .values(
                ended_at=datetime.now(timezone.utc),
                total_frames=total_frames,
                total_hazards=total_hazards,
            )
        )


async def increment_frame_count(session_id: str) -> None:
    async with get_session() as db:
        await db.execute(
            update(NavigationSession)
            .where(NavigationSession.session_id == session_id)
            .values(total_frames=NavigationSession.total_frames + 1)
        )


# ---------------------------------------------------------------------------
#  Scene snapshots
# ---------------------------------------------------------------------------

async def save_scene_snapshot(
    session_id: str,
    scene_json: dict,
    confidence: float = 0.0,
    direction: Optional[str] = None,
    distance_ft: Optional[float] = None,
) -> int:
    async with get_session() as db:
        snap = SceneSnapshot(
            session_id=session_id,
            scene_json=scene_json,
            confidence=confidence,
            clear_path_direction=direction,
            clear_path_distance_ft=distance_ft,
        )
        db.add(snap)
        await db.flush()
        return snap.id


async def get_recent_snapshots(
    session_id: str, limit: int = 30
) -> List[SceneSnapshot]:
    async with get_session() as db:
        result = await db.execute(
            select(SceneSnapshot)
            .where(SceneSnapshot.session_id == session_id)
            .order_by(SceneSnapshot.captured_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
#  Hazard events
# ---------------------------------------------------------------------------

async def save_hazard_event(
    session_id: str,
    hazard_type: str,
    urgency: str,
    direction: Optional[str] = None,
    distance_feet: Optional[float] = None,
) -> int:
    async with get_session() as db:
        evt = HazardEvent(
            session_id=session_id,
            hazard_type=hazard_type,
            urgency=urgency,
            direction=direction,
            distance_feet=distance_feet,
        )
        db.add(evt)
        await db.flush()
        return evt.id


async def get_session_hazards(session_id: str) -> List[HazardEvent]:
    async with get_session() as db:
        result = await db.execute(
            select(HazardEvent)
            .where(HazardEvent.session_id == session_id)
            .order_by(HazardEvent.detected_at.desc())
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
#  Spatial landmarks (queryable memory)
# ---------------------------------------------------------------------------

async def save_landmark(
    session_id: str,
    label: str,
    description: Optional[str] = None,
    direction: Optional[str] = None,
    distance_feet: Optional[float] = None,
    frame_index: int = 0,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    bbox: Optional[dict] = None,
) -> int:
    """Persist a landmark with optional PostGIS point and bounding box."""
    async with get_session() as db:
        lm = SpatialLandmark(
            session_id=session_id,
            label=label,
            description=description,
            direction_from_user=direction,
            distance_feet=distance_feet,
            frame_index=frame_index,
        )
        if lat is not None and lon is not None:
            from geoalchemy2.elements import WKTElement
            lm.position = WKTElement(f"POINT({lon} {lat})", srid=4326)
        if bbox:
            lm.bbox_ymin = bbox.get("ymin")
            lm.bbox_xmin = bbox.get("xmin")
            lm.bbox_ymax = bbox.get("ymax")
            lm.bbox_xmax = bbox.get("xmax")
        db.add(lm)
        await db.flush()
        return lm.id


async def search_landmarks(
    session_id: str,
    query: str,
    limit: int = 10,
) -> List[SpatialLandmark]:
    """Search landmarks by label substring (case-insensitive)."""
    async with get_session() as db:
        result = await db.execute(
            select(SpatialLandmark)
            .where(
                SpatialLandmark.session_id == session_id,
                SpatialLandmark.label.ilike(f"%{query}%"),
            )
            .order_by(SpatialLandmark.recorded_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def search_landmarks_near(
    session_id: str,
    lat: float,
    lon: float,
    radius_metres: float = 20.0,
    limit: int = 10,
) -> List[SpatialLandmark]:
    """Find landmarks within *radius_metres* of a GPS point using PostGIS."""
    async with get_session() as db:
        point = ST_MakePoint(lon, lat)
        result = await db.execute(
            select(SpatialLandmark)
            .where(
                SpatialLandmark.session_id == session_id,
                SpatialLandmark.position.isnot(None),
                ST_DWithin(
                    SpatialLandmark.position,
                    point,
                    radius_metres,
                    use_spheroid=False,
                ),
            )
            .order_by(SpatialLandmark.recorded_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_all_landmarks(session_id: str) -> List[SpatialLandmark]:
    """Return every landmark for a session, newest first."""
    async with get_session() as db:
        result = await db.execute(
            select(SpatialLandmark)
            .where(SpatialLandmark.session_id == session_id)
            .order_by(SpatialLandmark.recorded_at.desc())
        )
        return list(result.scalars().all())
