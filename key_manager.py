"""
Manages API keys per provider: round-robin rotation with cooldown on rate-limit errors.
"""

import json
import time
from pathlib import Path
from threading import Lock
from typing import Optional

DATA_FILE = Path(__file__).parent / "data" / "keys.json"
DATA_FILE.parent.mkdir(exist_ok=True)

_lock = Lock()


def _load() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def _save(data: dict):
    DATA_FILE.write_text(json.dumps(data, indent=2))


def get_all_keys() -> dict:
    with _lock:
        return _load()


def add_key(provider: str, key: str, label: str = "") -> dict:
    with _lock:
        data = _load()
        data.setdefault(provider, [])
        # avoid duplicates
        if any(k["key"] == key for k in data[provider]):
            return {"status": "duplicate"}
        entry = {
            "key": key,
            "label": label or f"{provider}-{len(data[provider]) + 1}",
            "requests": 0,
            "errors": 0,
            "cooldown_until": 0,
            "added_at": time.time(),
        }
        data[provider].append(entry)
        _save(data)
        return {"status": "added", "entry": entry}


def delete_key(provider: str, key: str) -> bool:
    with _lock:
        data = _load()
        before = len(data.get(provider, []))
        data[provider] = [k for k in data.get(provider, []) if k["key"] != key]
        _save(data)
        return len(data[provider]) < before


def pick_key(provider: str) -> Optional[str]:
    """Round-robin pick, skipping keys in cooldown."""
    with _lock:
        data = _load()
        keys = data.get(provider, [])
        if not keys:
            return None
        now = time.time()
        available = [k for k in keys if k["cooldown_until"] < now]
        if not available:
            # all in cooldown — pick the one whose cooldown expires soonest
            available = sorted(keys, key=lambda k: k["cooldown_until"])
        # pick the one with fewest requests
        chosen = min(available, key=lambda k: k["requests"])
        chosen["requests"] += 1
        _save(data)
        return chosen["key"]


def mark_error(provider: str, key: str, cooldown_seconds: int = 60):
    """Call when a key hits a rate-limit. Puts it in cooldown."""
    with _lock:
        data = _load()
        for k in data.get(provider, []):
            if k["key"] == key:
                k["errors"] += 1
                k["cooldown_until"] = time.time() + cooldown_seconds
                break
        _save(data)


def get_stats() -> dict:
    """Return per-provider, per-key stats for the dashboard."""
    with _lock:
        data = _load()
        now = time.time()
        out = {}
        for provider, keys in data.items():
            out[provider] = []
            for k in keys:
                masked = k["key"][:8] + "..." + k["key"][-4:]
                out[provider].append({
                    "label": k["label"],
                    "key_masked": masked,
                    "key": k["key"],
                    "requests": k["requests"],
                    "errors": k["errors"],
                    "in_cooldown": k["cooldown_until"] > now,
                    "cooldown_remaining": max(0, int(k["cooldown_until"] - now)),
                })
        return out
