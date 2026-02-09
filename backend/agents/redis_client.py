"""NaviSound Redis session-state & caching layer.

Uses redis.asyncio (redis-py ≥ 4.2) for fully async operations.
Stores:
 - Per-session state (last scene, direction, hazard count)
 - Frame history ring-buffer (configurable depth)
 - TTL-based expiry so old sessions auto-cleanup
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

logger = logging.getLogger("navisound.redis")

_pool: Optional[aioredis.Redis] = None

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SESSION_TTL = 3600  # 1 hour
FRAME_HISTORY_MAX = 100  # keep last N scene analysis results per session


async def init_redis() -> aioredis.Redis:
    """Create the global async Redis connection pool."""
    global _pool
    _pool = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    await _pool.ping()
    logger.info("Redis connected at %s", REDIS_URL)
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None
        logger.info("Redis connection closed")


def _r() -> aioredis.Redis:
    if _pool is None:
        raise RuntimeError("Redis not initialised – call init_redis() first")
    return _pool


# ---------------------------------------------------------------------------
#  Session state  (hash per session)
# ---------------------------------------------------------------------------

def _session_key(session_id: str) -> str:
    return f"nav:session:{session_id}"


async def set_session_state(session_id: str, data: Dict[str, Any]) -> None:
    """Upsert fields into the session hash and refresh TTL."""
    key = _session_key(session_id)
    r = _r()
    serialised = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in data.items()}
    await r.hset(key, mapping=serialised)
    await r.expire(key, SESSION_TTL)


async def get_session_state(session_id: str) -> Dict[str, Any]:
    key = _session_key(session_id)
    raw = await _r().hgetall(key)
    result: Dict[str, Any] = {}
    for k, v in raw.items():
        try:
            result[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            result[k] = v
    return result


async def delete_session(session_id: str) -> None:
    await _r().delete(_session_key(session_id))


# ---------------------------------------------------------------------------
#  Frame history  (list / ring buffer)
# ---------------------------------------------------------------------------

def _frame_key(session_id: str) -> str:
    return f"nav:frames:{session_id}"


async def push_frame_result(session_id: str, frame_result: dict) -> None:
    """Append a scene analysis result and keep only the last N entries."""
    key = _frame_key(session_id)
    r = _r()
    await r.rpush(key, json.dumps(frame_result))
    await r.ltrim(key, -FRAME_HISTORY_MAX, -1)  # keep last N
    await r.expire(key, SESSION_TTL)


async def get_frame_history(session_id: str, last_n: int = 10) -> List[dict]:
    """Get the most recent *last_n* frame results."""
    key = _frame_key(session_id)
    raw = await _r().lrange(key, -last_n, -1)
    return [json.loads(r) for r in raw]


async def get_frame_count(session_id: str) -> int:
    return await _r().llen(_frame_key(session_id))


# ---------------------------------------------------------------------------
#  Landmark cache (sorted-set by timestamp for quick recall)
# ---------------------------------------------------------------------------

def _landmark_key(session_id: str) -> str:
    return f"nav:landmarks:{session_id}"


async def cache_landmark(session_id: str, label: str, data: dict) -> None:
    """Cache a landmark for fast in-memory recall."""
    import time
    key = _landmark_key(session_id)
    r = _r()
    entry = json.dumps({"label": label, **data})
    await r.zadd(key, {entry: time.time()})
    await r.expire(key, SESSION_TTL)


async def recall_landmarks(session_id: str, query: str, limit: int = 5) -> List[dict]:
    """Return landmarks whose label contains *query* (case-insensitive)."""
    key = _landmark_key(session_id)
    all_entries = await _r().zrevrange(key, 0, -1)
    matches: List[dict] = []
    q = query.lower()
    for raw in all_entries:
        entry = json.loads(raw)
        if q in entry.get("label", "").lower() or q in json.dumps(entry).lower():
            matches.append(entry)
            if len(matches) >= limit:
                break
    return matches


# ---------------------------------------------------------------------------
#  Pub / Sub helpers (real-time hazard broadcast)
# ---------------------------------------------------------------------------

async def publish_hazard(session_id: str, hazard: dict) -> int:
    """Publish a hazard event to the session's channel."""
    channel = f"nav:hazards:{session_id}"
    return await _r().publish(channel, json.dumps(hazard))
