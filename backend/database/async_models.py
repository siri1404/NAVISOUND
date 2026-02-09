"""Async SQLAlchemy 2.0 ORM models with PostGIS geometry support."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class NavigationSession(Base):
    __tablename__ = "navigation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_frames: Mapped[int] = mapped_column(Integer, default=0)
    total_hazards: Mapped[int] = mapped_column(Integer, default=0)


class SceneSnapshot(Base):
    __tablename__ = "scene_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    scene_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    clear_path_direction: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    clear_path_distance_ft: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )


class HazardEvent(Base):
    __tablename__ = "hazard_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    hazard_type: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    distance_feet: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    was_avoided: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)


class SpatialLandmark(Base):
    """Stores remembered landmarks/features with PostGIS geometry for spatial recall.

    The position column stores a POINT(longitude latitude) representing
    relative position within the navigation space. When GPS is unavailable
    we use a local coordinate system (metres from session start).
    """

    __tablename__ = "spatial_landmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    direction_from_user: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    distance_feet: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frame_index: Mapped[int] = mapped_column(Integer, default=0)
    position = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )

    # Bounding box from Gemini spatial grounding (normalised 0-1000)
    bbox_ymin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_xmin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_ymax: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_xmax: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    testing_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    task_1_completion: Mapped[bool] = mapped_column(Boolean, default=False)
    task_1_time_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    task_1_collisions: Mapped[int] = mapped_column(Integer, default=0)
    task_2_completion: Mapped[bool] = mapped_column(Boolean, default=False)
    task_2_time_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    task_2_collisions: Mapped[int] = mapped_column(Integer, default=0)
    sus_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nps_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
