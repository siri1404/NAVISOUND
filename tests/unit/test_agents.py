"""Unit tests for the four NaviSound agents (mocked Gemini)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

# We patch at the module level since agents import GeminiLiveClient
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "backend", "agents"))

from agents.scene_agent import SceneAgent
from agents.hazard_agent import HazardAgent
from agents.navigation_agent import NavigationAgent
from agents.audio_feedback_agent import AudioFeedbackAgent


def _make_mock_client(return_value: dict):
    client = MagicMock()
    client.send_multimodal = AsyncMock(return_value=return_value)
    return client


# ── SceneAgent ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scene_agent_returns_scene():
    mock_response = {
        "obstacles": [{"name": "chair", "location": "left", "distance_feet": 3}],
        "clear_path": {"direction": "forward", "distance_feet": 10},
        "confidence": 0.9,
        "summary": "Clear path forward",
    }
    agent = SceneAgent(_make_mock_client(mock_response))
    result = await agent.analyze_frame("s1", "AAAA==")  # tiny fake b64

    assert result["clear_path"]["direction"] == "forward"
    assert result["confidence"] == 0.9
    assert len(agent.context_buffer) == 1


@pytest.mark.asyncio
async def test_scene_agent_empty_response():
    agent = SceneAgent(_make_mock_client({}))
    result = await agent.analyze_frame("s1", "AAAA==")
    assert result == {}


# ── HazardAgent ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hazard_agent_detects():
    mock_response = {
        "imminent_hazards": [{"type": "person-approaching", "direction": "left", "urgency": "CRITICAL"}],
        "safe_status": False,
        "recommended_action": "Stop",
    }
    agent = HazardAgent(_make_mock_client(mock_response))
    result = await agent.detect_hazards("s1", "AAAA==")

    assert len(result["imminent_hazards"]) == 1
    assert result["safe_status"] is False


@pytest.mark.asyncio
async def test_hazard_agent_with_audio():
    agent = HazardAgent(_make_mock_client({"imminent_hazards": [], "safe_status": True}))
    result = await agent.detect_hazards("s1", "AAAA==", "BBBB==")
    assert result["safe_status"] is True


# ── NavigationAgent ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_navigation_agent_routes():
    mock_response = {
        "next_direction": "forward-left",
        "distance_feet": 12,
        "next_milestone": "doorway",
        "turns_remaining": 1,
        "confidence": 0.85,
    }
    agent = NavigationAgent(_make_mock_client(mock_response))
    result = await agent.route_to_destination("s1", "exit", {})

    assert result["next_direction"] == "forward-left"
    assert result["distance_feet"] == 12
    assert len(agent.journey_log) == 1


# ── AudioFeedbackAgent ──────────────────────────────────────

@pytest.mark.asyncio
async def test_audio_agent_generates_params():
    mock_response = {
        "pan": -0.5,
        "volume": 0.8,
        "tone_hz": 400,
        "cadence_bpm": 100,
        "voice_instruction": "Turn left in 5 feet",
    }
    agent = AudioFeedbackAgent(_make_mock_client(mock_response))
    result = await agent.generate_audio_params("s1", {"type": "video_frame"})

    assert -1.0 <= result["pan"] <= 1.0
    assert result["voice_instruction"] == "Turn left in 5 feet"
