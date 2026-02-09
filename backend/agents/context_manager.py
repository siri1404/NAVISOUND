"""1 M-token context-window manager for NaviSound.

Uses the google-genai SDK's count_tokens() to track token usage in real time
and automatically prunes the oldest context when approaching the limit.

The Gemini 2.0 Flash model supports a 1 048 576 token context window; we
target 90 % utilisation so there is always room for the current turn.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

import google.genai as genai

logger = logging.getLogger("navisound.context_manager")

# Gemini 2.0 Flash Live – 1 M tokens
MAX_CONTEXT_TOKENS = 1_048_576
PRUNE_TARGET = int(MAX_CONTEXT_TOKENS * 0.90)  # start pruning at 90 %


@dataclass
class ContextEntry:
    """One turn / observation in the running context window."""
    role: str  # "user" | "model"
    text: str
    token_count: int = 0
    frame_index: int = 0
    entry_type: str = "observation"  # observation | landmark | hazard | route


@dataclass
class SessionContext:
    """Per-session context buffer with token accounting."""
    session_id: str
    entries: Deque[ContextEntry] = field(default_factory=deque)
    total_tokens: int = 0
    frame_counter: int = 0
    landmark_entries: List[ContextEntry] = field(default_factory=list)


class ContextManager:
    """Manages 1 M-token context windows across multiple sessions."""

    def __init__(self) -> None:
        self._model_name = os.getenv(
            "GEMINI_MODEL", "gemini-2.0-flash-live-preview-04-09"
        )
        self._project = os.getenv("GCP_PROJECT_ID", "navisound")
        self._region = os.getenv("GCP_REGION", "us-central1")
        self._client = genai.Client(
            vertexai=True,
            project=self._project,
            location=self._region,
        )
        self._sessions: Dict[str, SessionContext] = {}

    # ------------------------------------------------------------------
    #  Token counting
    # ------------------------------------------------------------------

    async def count_tokens(self, text: str) -> int:
        """Count tokens for a string using the Gemini API."""
        try:
            response = await self._client.aio.models.count_tokens(
                model=self._model_name,
                contents=text,
            )
            return response.total_tokens
        except Exception as exc:
            logger.warning("Token counting failed (%s); estimating", exc)
            # Rough estimate: ~4 chars per token
            return max(1, len(text) // 4)

    # ------------------------------------------------------------------
    #  Session lifecycle
    # ------------------------------------------------------------------

    def get_or_create(self, session_id: str) -> SessionContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionContext(session_id=session_id)
        return self._sessions[session_id]

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    #  Add entries
    # ------------------------------------------------------------------

    async def add_observation(
        self,
        session_id: str,
        text: str,
        entry_type: str = "observation",
    ) -> ContextEntry:
        """Add a new context entry, pruning old ones if needed."""
        ctx = self.get_or_create(session_id)

        tokens = await self.count_tokens(text)
        entry = ContextEntry(
            role="model",
            text=text,
            token_count=tokens,
            frame_index=ctx.frame_counter,
            entry_type=entry_type,
        )
        ctx.frame_counter += 1

        # Prune before adding if we'd exceed limit
        while ctx.total_tokens + tokens > PRUNE_TARGET and ctx.entries:
            removed = ctx.entries.popleft()
            ctx.total_tokens -= removed.token_count

        ctx.entries.append(entry)
        ctx.total_tokens += tokens

        # Keep landmark entries in a separate list (never pruned)
        if entry_type == "landmark":
            ctx.landmark_entries.append(entry)

        logger.debug(
            "Session %s: +%d tokens (%s), total=%d/%d",
            session_id, tokens, entry_type,
            ctx.total_tokens, MAX_CONTEXT_TOKENS,
        )
        return entry

    # ------------------------------------------------------------------
    #  Build context string for agent prompts
    # ------------------------------------------------------------------

    def build_context_string(
        self,
        session_id: str,
        max_entries: Optional[int] = None,
        include_landmarks: bool = True,
    ) -> str:
        """Build a string of recent context for agent prompts."""
        ctx = self.get_or_create(session_id)
        parts: List[str] = []

        # Always include landmark summaries first (persistent memory)
        if include_landmarks and ctx.landmark_entries:
            parts.append("=== KNOWN LANDMARKS ===")
            for lm in ctx.landmark_entries[-50:]:  # last 50 landmarks
                parts.append(f"[frame {lm.frame_index}] {lm.text}")
            parts.append("")

        # Recent observations
        entries = list(ctx.entries)
        if max_entries:
            entries = entries[-max_entries:]

        if entries:
            parts.append("=== RECENT OBSERVATIONS ===")
            for e in entries:
                parts.append(f"[frame {e.frame_index}] {e.text}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    #  Stats
    # ------------------------------------------------------------------

    def get_stats(self, session_id: str) -> dict:
        ctx = self.get_or_create(session_id)
        return {
            "total_tokens": ctx.total_tokens,
            "max_tokens": MAX_CONTEXT_TOKENS,
            "utilisation_pct": round(ctx.total_tokens / MAX_CONTEXT_TOKENS * 100, 1),
            "entry_count": len(ctx.entries),
            "landmark_count": len(ctx.landmark_entries),
            "frame_counter": ctx.frame_counter,
        }
