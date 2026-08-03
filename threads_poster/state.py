"""Tiny persisted state, separate from the token: currently just when we last
published, so the loop can space publishes out (rate limiting) across passes,
restarts, and VM reboots."""

import json
import os


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def last_publish(path: str) -> int:
    return int(_load(path).get("last_publish", 0))


def record_publish(path: str, ts: int) -> None:
    data = _load(path)
    data["last_publish"] = ts
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)
