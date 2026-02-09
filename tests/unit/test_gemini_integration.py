"""Unit tests for GeminiLiveClient (mocked SDK calls)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "backend", "agents"))

from gemini_client import GeminiLiveClient


def _mock_session(text_response: str):
    """Create a mock AsyncSession that yields the given text."""
    session = AsyncMock()

    # Build a fake server_content message
    part = MagicMock()
    part.text = text_response

    model_turn = MagicMock()
    model_turn.parts = [part]

    server_content = MagicMock()
    server_content.model_turn = model_turn
    server_content.turn_complete = True

    msg = MagicMock()
    msg.server_content = server_content

    async def _receive():
        yield msg

    session.receive = _receive
    session.send_client_content = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_send_multimodal_text_only():
    client = GeminiLiveClient()
    session = _mock_session('{"direction": "forward", "distance_feet": 10}')
    client.sessions["s1"] = session

    result = await client.send_multimodal("s1", text="Navigate forward")
    assert result["direction"] == "forward"
    assert result["distance_feet"] == 10


@pytest.mark.asyncio
async def test_send_multimodal_strips_code_fences():
    client = GeminiLiveClient()
    fenced = '```json\n{"direction": "left"}\n```'
    session = _mock_session(fenced)
    client.sessions["s1"] = session

    result = await client.send_multimodal("s1", text="test")
    assert result["direction"] == "left"


@pytest.mark.asyncio
async def test_send_multimodal_non_json_returns_empty():
    client = GeminiLiveClient()
    session = _mock_session("I don't understand.")
    client.sessions["s1"] = session

    result = await client.send_multimodal("s1", text="test")
    assert result == {}


@pytest.mark.asyncio
async def test_session_not_found_raises():
    client = GeminiLiveClient()
    with pytest.raises(RuntimeError, match="Session not found"):
        await client.send_multimodal("nonexistent", text="hello")


@pytest.mark.asyncio
async def test_close_session():
    client = GeminiLiveClient()
    cm = AsyncMock()
    client._session_cms["s1"] = cm
    client.sessions["s1"] = MagicMock()

    await client.close_session("s1")
    assert "s1" not in client.sessions
    assert "s1" not in client._session_cms
