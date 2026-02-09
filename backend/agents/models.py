"""NaviSound data models for agent communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "CRITICAL"


@dataclass
class Obstacle:
    name: str
    location: str  # e.g. "left", "center", "right"
    distance_feet: float
    height: str = "unknown"  # e.g. "ankle", "waist", "overhead"
    urgency: Urgency = Urgency.MEDIUM


@dataclass
class FloorHazard:
    type: str  # e.g. "cable", "wet_floor", "step"
    location: str
    urgency: Urgency = Urgency.HIGH


@dataclass
class ClearPath:
    direction: str  # e.g. "forward-right"
    distance_feet: float = 0.0


@dataclass
class SceneResult:
    obstacles: List[Obstacle] = field(default_factory=list)
    clear_path: Optional[ClearPath] = None
    floor_hazards: List[FloorHazard] = field(default_factory=list)
    spatial_features: List[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""


@dataclass
class Hazard:
    type: str  # e.g. "person-approaching", "stairs", "vehicle"
    direction: str = ""
    distance_feet: float = 0.0
    speed: str = ""  # e.g. "fast", "slow", "stationary"
    urgency: Urgency = Urgency.MEDIUM
    warning_lead_time_sec: float = 0.0


@dataclass
class HazardResult:
    imminent_hazards: List[Hazard] = field(default_factory=list)
    predicted_hazards: List[Hazard] = field(default_factory=list)
    safe_status: bool = True
    recommended_action: str = ""


@dataclass
class Route:
    next_direction: str = ""
    distance_feet: float = 0.0
    next_milestone: str = ""
    turns_remaining: int = 0
    estimated_time_sec: float = 0.0
    confidence: float = 0.0


@dataclass
class AudioParams:
    pan: float = 0.0  # -1.0 (left) to 1.0 (right)
    volume: float = 0.5  # 0.0 to 1.0
    tone_hz: int = 600  # 200 to 1200
    cadence_bpm: int = 80  # 40 to 160
    voice_instruction: str = ""
