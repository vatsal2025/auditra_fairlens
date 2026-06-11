"""
Session store with disk persistence.
In-memory cache for speed; pickle-backed files survive server restarts
within the same container (e.g. Railway crashes/redeploys won't wipe sessions
as long as /tmp survives, which it does across process restarts on the same host).
"""
import logging
import os
import pickle
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SESSIONS_DIR = os.environ.get("SESSIONS_DIR", "/tmp/fairlens_sessions")

# Keys that can't be pickled — keep in memory only
_NO_PERSIST = {"audit_proc"}

_cache: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.pkl")


def _load_from_disk(session_id: str) -> None:
    p = _path(session_id)
    if not os.path.exists(p):
        return
    try:
        with open(p, "rb") as f:
            data = pickle.load(f)
        _cache[session_id] = data
    except Exception as e:
        logger.warning("Failed to load session %s from disk: %s", session_id, e)


def _persist(session_id: str) -> None:
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        data = {k: v for k, v in _cache[session_id].items() if k not in _NO_PERSIST}
        with open(_path(session_id), "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.warning("Failed to persist session %s: %s", session_id, e)


def set(session_id: str, key: str, value: Any) -> None:
    with _lock:
        if session_id not in _cache:
            _cache[session_id] = {}
        _cache[session_id][key] = value
        if key not in _NO_PERSIST:
            _persist(session_id)


def get(session_id: str, key: str) -> Optional[Any]:
    with _lock:
        if session_id not in _cache:
            _load_from_disk(session_id)
        return _cache.get(session_id, {}).get(key)


def exists(session_id: str) -> bool:
    with _lock:
        if session_id in _cache:
            return True
        _load_from_disk(session_id)
        return session_id in _cache


def delete(session_id: str) -> None:
    with _lock:
        _cache.pop(session_id, None)
        p = _path(session_id)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
