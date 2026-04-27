"""
events.py
Event schema and publisher for Echo's Webcam Intelligence Module.

Events go to two places:
  1. In-memory queue — for any local subscriber in the same process
  2. HTTP POST to echo_server.py — so the GUI and other modules can react

Schema matches the Copilot prompt spec exactly.
"""

import queue
import threading
import requests
from datetime import datetime, timezone

# ── In-memory event bus ───────────────────────────────────────────────────────
_subscribers: list = []
_lock = threading.Lock()

def subscribe(callback):
    """Register a callable that receives every event dict."""
    with _lock:
        _subscribers.append(callback)

def _notify(event: dict):
    with _lock:
        subs = list(_subscribers)
    for cb in subs:
        try:
            cb(event)
        except Exception as e:
            print(f"[events] Subscriber error: {e}", flush=True)

# ── Echo server endpoint ──────────────────────────────────────────────────────
ECHO_SERVER_URL = "http://localhost:5050/api/webcam/event"
_post_enabled   = True

def _post_to_server(event: dict):
    if not _post_enabled:
        return
    try:
        requests.post(ECHO_SERVER_URL, json=event, timeout=2)
    except Exception:
        pass  # Server might not be running — silent fail

# ── Event builder ─────────────────────────────────────────────────────────────

def build_event(
    frame_id:   int,
    faces:      list,
    gestures:   list,
    emotions:   list,
    meta:       dict,
) -> dict:
    """
    Build the normalized event dict.

    faces:    [{id, confidence, bbox}]
    gestures: [{type, confidence, bbox}]
    emotions: [{label, confidence}] — parallel to faces
    meta:     {frame_width, frame_height, fps}
    """
    known_ids = [f["id"] for f in faces if f["id"] != "unknown"]

    # Merge emotion into face entries
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
    """Send event to all subscribers and to echo_server."""
    _notify(event)
    threading.Thread(target=_post_to_server, args=(event,), daemon=True).start()
