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

# Base64-encoded seed keys (loaded on first run if data file is empty)
_SEED = "eyJnZW1pbmkiOiBbeyJrZXkiOiAiQVEuQWI4Uk42SnhPbXk4UW1WVmY0dTV3YTBZcXdOd0kyQVh2a3ZlTWhmcFhoM0hrMzE4SFEiLCAibGFiZWwiOiAiZ2VtaW5pLTEiLCAicmVxdWVzdHMiOiAwLCAiZXJyb3JzIjogMCwgImNvb2xkb3duX3VudGlsIjogMCwgImFkZGVkX2F0IjogMH0sIHsia2V5IjogIkFRLkFiOFJONkozeDRfdWJUR1JkZVhIaW9TYko5ZV83dlpzWHRhaXY4T2tPNVJEczEtVlh3IiwgImxhYmVsIjogImdlbWluaS0yIiwgInJlcXVlc3RzIjogMCwgImVycm9ycyI6IDAsICJjb29sZG93bl91bnRpbCI6IDAsICJhZGRlZF9hdCI6IDB9XSwgImdyb3EiOiBbeyJrZXkiOiAiZ3NrX3BSMXRqMHBxcVVrTTA2dWplUUZCV0dkeWIzRllpMEhDZmRTcTBUdzJxb3JxdUNwMkFWc1AiLCAibGFiZWwiOiAiZ3JvcS0xIiwgInJlcXVlc3RzIjogMCwgImVycm9ycyI6IDAsICJjb29sZG93bl91bnRpbCI6IDAsICJhZGRlZF9hdCI6IDB9LCB7ImtleSI6ICJnc2tfaVAwRFlqTGJMRDRiUGtGWGIyN0lXR2R5YjNGWW40OVpoQjVKaDJRM0ROaTZOZWJVRGFHQSIsICJsYWJlbCI6ICJncm9xLTIiLCAicmVxdWVzdHMiOiAwLCAiZXJyb3JzIjogMCwgImNvb2xkb3duX3VudGlsIjogMCwgImFkZGVkX2F0IjogMH1dLCAib3BlbnJvdXRlciI6IFt7ImtleSI6ICJzay1vci12MS1iMzY2OTgwNTVhMjgwZWVmZDVhZmJkM2ZkODE0ZjkwODRlYmQ3MjViYzM1NWYyNDBhNzQ2MjY2YjdiZTMwODVkIiwgImxhYmVsIjogIm9wZW5yb3V0ZXItMSIsICJyZXF1ZXN0cyI6IDAsICJlcnJvcnMiOiAwLCAiY29vbGRvd25fdW50aWwiOiAwLCAiYWRkZWRfYXQiOiAwfSwgeyJrZXkiOiAic2stb3ItdjEtMjg2MTU0YTUxZmVhODNjYWE3ZjE3M2VlMzhmY2Q2MzgxM2Y4ZTMwZmM5OGYzOWRlMDBmMmJmM2MzMThiODM1OSIsICJsYWJlbCI6ICJvcGVucm91dGVyLTIiLCAicmVxdWVzdHMiOiAwLCAiZXJyb3JzIjogMCwgImNvb2xkb3duX3VudGlsIjogMCwgImFkZGVkX2F0IjogMH1dLCAiY29oZXJlIjogW3sia2V5IjogImpvSThpWklqWm1oTkY4N0w0UHlxYk50SDE1Y3NMU3Z4N0FWZmQ1R2kiLCAibGFiZWwiOiAiY29oZXJlLTEiLCAicmVxdWVzdHMiOiAwLCAiZXJyb3JzIjogMCwgImNvb2xkb3duX3VudGlsIjogMCwgImFkZGVkX2F0IjogMH0sIHsia2V5IjogImtuQm1WWTRQdFU4YnNPbDNXVXFKSWlGY2dLVnFiMjFNOGE1ZGR1M3IiLCAibGFiZWwiOiAiY29oZXJlLTIiLCAicmVxdWVzdHMiOiAwLCAiZXJyb3JzIjogMCwgImNvb2xkb3duX3VudGlsIjogMCwgImFkZGVkX2F0IjogMH1dfQ=="

def _seed_if_empty():
    data = _load()
    if not any(data.get(p) for p in data):
        import base64 as _b64
        seeded = json.loads(_b64.b64decode(_SEED).decode())
        _save(seeded)




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
