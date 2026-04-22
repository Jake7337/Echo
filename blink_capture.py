"""
blink_capture.py
Stage 1 of Echo's Blink pipeline — fast, no thinking, just grab.

When BlinkPy detects motion:
  1. Download thumbnail locally
  2. Download clip locally
  3. Save a stable JSON event file
  4. Return the local paths to the caller

Echo never touches Blink's expiring signed URLs after this runs.
"""

import os
import json
import time
import asyncio
from datetime import datetime

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(BASE_DIR, "cache", "blink")
THUMB_DIR  = os.path.join(CACHE_DIR, "thumbs")
CLIP_DIR   = os.path.join(CACHE_DIR, "clips")
EVENT_DIR  = os.path.join(CACHE_DIR, "events")
ECHO_EVENT_FILE = os.path.join(CACHE_DIR, "latest_event.json")

# Max age of cached clips before cleanup (seconds) — 24 hours
CACHE_MAX_AGE = 86400

# ── Setup ─────────────────────────────────────────────────────────────────────

for d in (THUMB_DIR, CLIP_DIR, EVENT_DIR):
    os.makedirs(d, exist_ok=True)


# ── Fetch clip metadata from Blink ────────────────────────────────────────────

async def fetch_clip_metadata(blink, camera_name: str) -> dict:
    """Pull the most recent clip entry for this camera from Blink's API."""
    from blinkpy import api as blink_api
    try:
        data = await blink_api.request_videos(blink, time=time.time() - 120, page=0)
        if not isinstance(data, dict):
            return {}
        for item in data.get("media", []):
            if item.get("device_name") == camera_name:
                meta        = {}
                raw_meta    = item.get("metadata") or "{}"
                try:
                    meta = json.loads(raw_meta)
                except Exception:
                    pass
                return {
                    "clip_url":    item.get("media", ""),
                    "thumb_url":   item.get("thumbnail", ""),
                    "description": (item.get("description", "") or
                                    meta.get("description", "") or "").strip(),
                    "cv_detection": meta.get("cv_detection", []),
                    "media_id":    item.get("id", ""),
                }
    except Exception as e:
        print(f"[capture] fetch_clip_metadata error: {e}", flush=True)
    return {}


# ── Download helpers ──────────────────────────────────────────────────────────

async def _download_via_blink(blink, url: str, dest_path: str) -> bool:
    """Download a Blink media URL using blinkpy's authenticated session."""
    if not url:
        return False
    print(f"[capture] downloading: {url}", flush=True)
    try:
        from blinkpy import api as blink_api
        response = await blink_api.http_get(blink, url=url, stream=True, json=False)
        if response is None:
            print(f"[capture] no response", flush=True)
            return False
        if hasattr(response, "status"):
            if response.status == 200:
                content = await response.read()
                with open(dest_path, "wb") as f:
                    f.write(content)
                return True
            print(f"[capture] download failed {response.status}: {url}", flush=True)
            return False
        if hasattr(response, "status_code"):
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(response.content)
                return True
            print(f"[capture] download failed {response.status_code}: {url}", flush=True)
    except Exception as e:
        print(f"[capture] download error: {e}", flush=True)
    return False


# ── Main capture function ─────────────────────────────────────────────────────

async def capture_event(blink, camera_name: str, thumbnail_url: str = None) -> dict:
    """
    Immediately capture all event data for a camera motion.
    Returns a stable local event dict — no expiring URLs.

    Call this as soon as motion is detected, before any processing.
    """
    ts        = int(time.time())
    dt_str    = datetime.fromtimestamp(ts).strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = camera_name.lower().replace(" ", "_")
    prefix    = f"{safe_name}_{dt_str}"

    event = {
        "camera":      camera_name,
        "timestamp":   ts,
        "datetime":    datetime.fromtimestamp(ts).isoformat(),
        "description": "",
        "cv_detection": [],
        "thumbnail":   None,
        "clip":        None,
        "media_id":    "",
    }

    # Step 1 — grab clip metadata from Blink (fast, just JSON)
    meta = await fetch_clip_metadata(blink, camera_name)
    if meta:
        event["description"]  = meta.get("description", "")
        event["cv_detection"] = meta.get("cv_detection", [])
        event["media_id"]     = meta.get("media_id", "")

    # Step 2 — download thumbnail
    thumb_src = thumbnail_url or meta.get("thumb_url", "")
    if thumb_src:
        # Blink thumbnails sometimes come without extension
        ext = ".jpg" if ".jpg" in thumb_src else ".png" if ".png" in thumb_src else ".jpg"
        thumb_path = os.path.join(THUMB_DIR, f"{prefix}{ext}")
        if await _download_via_blink(blink, thumb_src, thumb_path):
            event["thumbnail"] = thumb_path
            print(f"[capture] thumbnail saved: {os.path.basename(thumb_path)}", flush=True)
        else:
            print(f"[capture] thumbnail download failed", flush=True)

    # Step 3 — download clip
    clip_src = meta.get("clip_url", "")
    if clip_src:
        clip_path = os.path.join(CLIP_DIR, f"{prefix}.mp4")
        if await _download_via_blink(blink, clip_src, clip_path):
            event["clip"] = clip_path
            print(f"[capture] clip saved: {os.path.basename(clip_path)}", flush=True)
        else:
            print(f"[capture] clip download failed (may not be ready yet)", flush=True)

    # Step 4 — write event JSON
    event_path = os.path.join(EVENT_DIR, f"{prefix}.json")
    with open(event_path, "w") as f:
        json.dump(event, f, indent=2)
    event["event_file"] = event_path

    # Step 5 — write latest_event.json so other modules can poll it
    with open(ECHO_EVENT_FILE, "w") as f:
        json.dump(event, f, indent=2)

    print(f"[capture] event saved: {event_path}", flush=True)
    print(f"[capture] description: {repr(event['description']) or '(none yet)'}", flush=True)

    return event


# ── Cache cleanup ─────────────────────────────────────────────────────────────

def cleanup_cache(max_age: int = CACHE_MAX_AGE):
    """Delete cached files older than max_age seconds. Call periodically."""
    now = time.time()
    removed = 0
    for folder in (THUMB_DIR, CLIP_DIR, EVENT_DIR):
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            try:
                if now - os.path.getmtime(fpath) > max_age:
                    os.remove(fpath)
                    removed += 1
            except Exception:
                pass
    if removed:
        print(f"[capture] cleanup: removed {removed} old cache files", flush=True)


# ── Read latest event (for other modules) ────────────────────────────────────

def get_latest_event() -> dict:
    """Read the most recent captured event. Returns {} if none."""
    try:
        with open(ECHO_EVENT_FILE) as f:
            return json.load(f)
    except Exception:
        return {}
