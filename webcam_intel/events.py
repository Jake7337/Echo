"""
events.py
Event schema and publisher for Echo's Webcam Intelligence Module.
All network/IO is wrapped in try/except — publish never raises.
"""

import logging
import threading
import requests
from datetime import datetime, timezone

log = logging.getLogger("webcam_intel.events")

# ── In-memory event bus ───────────────────────────────────────────────────────

_subscribers: list = []
_sub_lock = threading.Lock()

def subscribe(callback):
    with _sub_lock:
        _subscribers.append(callback)

def _notify(event: dict):
    with _sub_lock:
        subs = list(_subscribers)
    for cb in subs:
        try:
            cb(event)
        except Exception as e:
            log.warning("Subscriber error: %s", e)

# ── Echo server endpoint ──────────────────────────────────────────────────────

ECHO_SERVER_URL = "http://localhost:5050/api/webcam/event"
_post_enabled   = True

def _post_to_server(event: dict):
    if not _post_enabled:
        return
    try:
        requests.post(ECHO_SERVER_URL, json=event, timeout=2)
    except Exception as e:
        log.debug("POST to echo_server failed (server may not be running): %s", e)

# ── Event builder ─────────────────────────────────────────────────────────────

def build_event(
    frame_id:   int,
    faces:      list,
    gestures:   list,
    emotions:   list,
    meta:       dict,
) -> dict:
    known_ids = [f["id"] for f in faces if f["id"] != "unknown"]

    face_records = []
    for i, face in enumerate(faces):
        emotion = emotions[i] if i < len(emotions) else {"label": "unknown", "confidence": 0.0}
        face_records.append({
            "id":         face["id"],
            "confidence": face["confidence"],
            "bbox":       face["bbox"],
            "emotion":    emotion,
        })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "webcam.c920s",
        "frame_id":  frame_id,
        "faces":     face_records,
        "gestures":  gestures,
        "presence": {
            "any_person":   len(faces) > 0,
            "known_person": len(known_ids) > 0,
            "known_ids":    known_ids,
            "num_faces":    len(faces),
        },
        "raw_metadata": meta,
    }

# ── Publisher ─────────────────────────────────────────────────────────────────

def publish(event: dict):
    """Send event to all subscribers and to echo_server. Never raises."""
    try:
        _notify(event)
    except Exception as e:
        log.warning("_notify error: %s", e)
    try:
        threading.Thread(target=_post_to_server, args=(event,), daemon=True).start()
    except Exception as e:
        log.warning("Failed to start post thread: %s", e)
