"""Unit tests for the FastAPI orchestrator (mocked agents)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "backend", "agents"))

# We need to mock the GeminiLiveClient before importing orchestrator
with patch.dict(os.environ, {
    "GCP_PROJECT_ID": "navisound",
    "GCP_REGION": "us-central1",
    "GEMINI_MODEL": "gemini-2.0-flash-live-preview-04-09",
}):
    # Patch the client constructor so it doesn't try to connect to Vertex
    with patch("gemini_client.genai"):
        from orchestrator import orchestrate, active_sessions, scene_agent, hazard_agent, nav_agent, audio_agent


@pytest.fixture(autouse=True)
def reset_sessions():
    active_sessions.clear()
    active_sessions["test-session"] = {
        "last_clear_direction": None,
        "last_clear_distance": None,
    }
    yield
    active_sessions.clear()


@pytest.mark.asyncio
async def test_orchestrate_video_frame():
    scene_agent.analyze_frame = AsyncMock(return_value={
        "clear_path": {"direction": "forward", "distance_feet": 10},
        "confidence": 0.9,
    })
    hazard_agent.detect_hazards = AsyncMock(return_value={
        "imminent_hazards": [{"type": "chair", "urgency": "medium"}],
    })
    audio_agent.generate_audio_params = AsyncMock(return_value={
        "pan": 0.0, "volume": 0.6, "tone_hz": 600,
    })

    result = await orchestrate("test-session", {
        "type": "video_frame",
        "data": "AAAA==",
        "timestamp": 1.0,
    })

    assert result["navigation"]["direction"] == "forward"
    assert len(result["hazards"]) == 1
    assert "audio" in result
    assert result["confidence"] <= 0.9


@pytest.mark.asyncio
async def test_orchestrate_text_query():
    nav_agent.route_to_destination = AsyncMock(return_value={
        "next_direction": "left",
        "distance_feet": 5,
        "confidence": 0.8,
    })

    result = await orchestrate("test-session", {
        "type": "text_query",
        "destination": "exit",
    })

    assert result["next_direction"] == "left"


@pytest.mark.asyncio
async def test_orchestrate_voice_command_where():
    nav_agent.route_to_destination = AsyncMock(return_value={
        "next_direction": "forward",
        "distance_feet": 0,
    })

    result = await orchestrate("test-session", {
        "type": "voice_command",
        "text": "Where am I?",
    })

    assert "next_direction" in result


@pytest.mark.asyncio
async def test_orchestrate_agent_failure_does_not_crash():
    """If one agent throws, we still get partial results."""
    scene_agent.analyze_frame = AsyncMock(side_effect=RuntimeError("boom"))
    hazard_agent.detect_hazards = AsyncMock(return_value={
        "imminent_hazards": [],
    })
    audio_agent.generate_audio_params = AsyncMock(return_value={
        "pan": 0.0,
    })

    result = await orchestrate("test-session", {
        "type": "video_frame",
        "data": "AAAA==",
        "timestamp": 1.0,
    })

    # scene_agent failed → navigation will be empty dict fields
    assert "hazards" in result
    assert "audio" in result
