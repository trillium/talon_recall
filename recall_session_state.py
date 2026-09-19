"""Recall Session State - Read/cache Claude Code session pill states.

Reads ~/.claude/PAI/MEMORY/STATE/session-pills.jsonl (JSONL, one event
per line); latest event per session_id wins. 50ms TTL cache.
Pure Python, no third-party imports. All errors -> None / {}.
"""
import json
import time
from pathlib import Path

_STATE_FILE = Path.home() / ".claude" / "PAI" / "MEMORY" / "STATE" / "session-pills.jsonl"
_TTL_SECONDS = 0.05
_MAX_LINES = 1000
_cache: dict = {}
_cache_time: float = 0.0

def _refresh() -> None:
    """Re-read the JSONL and rebuild the cache. Silent on any error."""
    global _cache, _cache_time
    _cache_time = time.monotonic()
    try:
        with _STATE_FILE.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, ValueError):
        _cache = {}
        return
    new_cache: dict = {}
    for line in lines[-_MAX_LINES:]:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        sid = event.get("session_id") if isinstance(event, dict) else None
        if isinstance(sid, str) and sid:
            new_cache[sid] = event
    _cache = new_cache

def _ensure_fresh() -> None:
    if (time.monotonic() - _cache_time) >= _TTL_SECONDS:
        _refresh()

def get_session_status(session_id: str) -> dict | None:
    """Return latest state for a session_id, or None if unknown."""
    try:
        _ensure_fresh()
        return _cache.get(session_id)
    except Exception:
        return None

def get_all_session_states() -> dict[str, dict]:
    """Return all known session states, keyed by session_id."""
    try:
        _ensure_fresh()
        return dict(_cache)
    except Exception:
        return {}

def get_most_active_session() -> dict | None:
    """Return the most recently active non-idle session, or None if all idle."""
    try:
        states = get_all_session_states()
        active = [s for s in states.values() if s.get("status") != "idle"]
        if not active:
            return None
        return max(active, key=lambda s: s.get("timestamp", ""))
    except Exception:
        return None

def get_session_for_path(path: str) -> dict | None:
    """Return the most recent session whose cwd matches path, or None.

    Matches if the session's cwd equals path, or if path starts with cwd
    (handles subdirectory sessions). Returns None if no match found.
    """
    try:
        if not path:
            return None
        states = get_all_session_states()
        matches = [
            s for s in states.values()
            if s.get("cwd") and (
                s["cwd"] == path or path.startswith(s["cwd"])
            )
        ]
        if not matches:
            return None
        # Among matches, prefer most recently active
        active = [s for s in matches if s.get("status") != "idle"]
        pool = active if active else matches
        return max(pool, key=lambda s: s.get("timestamp", ""))
    except Exception:
        return None

def _strip_dev(t: str) -> str:
    return t[5:] if t.startswith("/dev/") else t

def get_session_by_tty(tty: str) -> dict | None:
    """Return the most recent session whose tty matches, or None.

    Normalizes /dev/ prefix on both sides. Prefers non-idle sessions;
    falls back to most-recent-any if all matches are idle.
    """
    try:
        if not tty:
            return None
        needle = _strip_dev(tty)
        states = get_all_session_states()
        matches = [s for s in states.values() if s.get("tty") and _strip_dev(s["tty"]) == needle]
        if not matches:
            return None
        active = [s for s in matches if s.get("status") != "idle"]
        pool = active if active else matches
        return max(pool, key=lambda s: s.get("timestamp", ""))
    except Exception:
        return None
