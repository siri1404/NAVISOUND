"""SQLAlchemy ORM models for NaviSound persistence layer."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime, Text, JSON,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class NavigationSession(Base):
    __tablename__ = "navigation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(64), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    total_frames = Column(Integer, default=0)
    total_hazards_detected = Column(Integer, default=0)


class SceneSnapshot(Base):
    __tablename__ = "scene_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    scene_json = Column(JSON, nullable=True)
    confidence = Column(Float, default=0.0)
    clear_path_direction = Column(String(32), nullable=True)
    clear_path_distance_ft = Column(Float, nullable=True)


class HazardEvent(Base):
    __tablename__ = "hazard_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    hazard_type = Column(String(64), nullable=False)
    direction = Column(String(32), nullable=True)
    distance_feet = Column(Float, nullable=True)
    urgency = Column(String(16), nullable=False)
    was_avoided = Column(Boolean, nullable=True)


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(String(64), nullable=False)
    testing_date = Column(DateTime, default=datetime.utcnow)
    task_1_completion = Column(Boolean, default=False)
    task_1_time_sec = Column(Float, nullable=True)
    task_1_collisions = Column(Integer, default=0)
    task_2_completion = Column(Boolean, default=False)
    task_2_time_sec = Column(Float, nullable=True)
    task_2_collisions = Column(Integer, default=0)
    sus_score = Column(Integer, nullable=True)
    nps_score = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)


def get_engine(url: str = "postgresql://user:pass@localhost:5432/navisound"):
    return create_engine(url, echo=False)


def init_db(engine=None):
    """Create all tables."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
