"""
In-memory session store. For hackathon use; replace with Redis in production.
Stores uploaded DataFrames and audit results keyed by session_id.
"""
from typing import Dict, Any, Optional
import threading

_store: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def set(session_id: str, key: str, value: Any) -> None:
    with _lock:
        if session_id not in _store:
            _store[session_id] = {}
        _store[session_id][key] = value


def get(session_id: str, key: str) -> Optional[Any]:
    with _lock:
        return _store.get(session_id, {}).get(key)


def exists(session_id: str) -> bool:
    with _lock:
        return session_id in _store


def delete(session_id: str) -> None:
    with _lock:
        _store.pop(session_id, None)
