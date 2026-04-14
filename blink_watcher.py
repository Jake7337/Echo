"""
blink_watcher.py
Watches Blink cameras for motion and has Echo announce it out loud.
Run this alongside echo_voice.py or on its own.
"""

import json
import os
import time
import asyncio
import requests
from datetime import datetime
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

CREDS_FILE   = os.path.join(os.path.dirname(__file__), "blink_creds.json")
POLL_SECONDS = 30
PI_SPEAK_URL = "http://192.168.68.84:5100/speak"

# ── Voice — routed to Pi speakers ─────────────────────────────────────────────

def speak(text: str):
    print(f"Echo: {text}", flush=True)
    try:
        requests.post(PI_SPEAK_URL, json={"text": text}, timeout=10)
    except Exception as e:
        print(f"[blink] speak failed — Pi unreachable? {e}", flush=True)

# ── Blink ──────────────────────────────────────────────────────────────────────

BLINK_SESSION_FILE = os.path.join(os.path.dirname(__file__), "blink_session.json")

async def setup_blink():
    with open(CREDS_FILE) as f:
        creds = json.load(f)

    blink = Blink(motion_interval=POLL_SECONDS)

    if os.path.exists(BLINK_SESSION_FILE):
        print("Loading saved session...", flush=True)
        with open(BLINK_SESSION_FILE) as f:
            saved = json.load(f)
        auth = Auth(saved, no_prompt=True)
    else:
        auth = Auth({"username": creds["username"], "password": creds["password"]}, no_prompt=True)

    blink.auth = auth

    try:
        await blink.start()
        print("Blink connected.", flush=True)
    except Exception:
        print("2FA required — check your email/phone for a code.", flush=True)
        code = input("Enter Blink 2FA code: ").strip()
        await blink.auth.complete_2fa_login(code)
        blink.setup_urls()
        await blink.get_homescreen()
        await blink.setup_post_verify()

    import time
    blink.last_refresh = int(time.time())

    if blink.urls:
        await blink.save(BLINK_SESSION_FILE)
        print("Session saved.", flush=True)

    # Arm all sync modules so motion detection works
    for name, sync in blink.sync.items():
        if not sync.arm:
            print(f"Arming {name}...", flush=True)
            await sync.async_arm(True)

    return blink

def build_announcement(camera_name: str, cv_detection: list) -> str:
    """Turn camera name + cv_detection list into a natural announcement."""
    if not cv_detection:
        return f"Motion detected on {camera_name}."
    objects = cv_detection
    if len(objects) == 1:
        label = objects[0]
    else:
        label = ", ".join(objects[:-1]) + " and " + objects[-1]
    return f"{label.capitalize()} detected on {camera_name}."


async def get_cv_detection(blink, camera_name: str) -> list:
    """
    Fetch the most recent media event for this camera and return cv_detection.
    Called only when a thumbnail change is detected — not on every poll.
    """
    from blinkpy import api as blink_api
    try:
        data = await blink_api.request_videos(blink, time=time.time() - 120, page=0)
        if not isinstance(data, dict):
            return []
        for item in data.get("media", []):
            if item.get("device_name") == camera_name:
                metadata_raw = item.get("metadata") or "{}"
                try:
                    metadata = json.loads(metadata_raw)
                    return metadata.get("cv_detection", [])
                except Exception:
                    return []
    except Exception:
        pass
    return []


async def watch(blink: Blink):
    print("Echo is watching the cameras...\n")

    # Seed thumbnails — only announce changes from this point forward
    await blink.refresh()
    last_thumbnails = {name: cam.thumbnail for name, cam in blink.cameras.items()}
    print(f"Watching {len(last_thumbnails)} cameras...", flush=True)

    while True:
        await asyncio.sleep(POLL_SECONDS)
        await blink.refresh()

        for name, camera in blink.cameras.items():
            new_thumb = camera.thumbnail
            if new_thumb and new_thumb != last_thumbnails.get(name):
                last_thumbnails[name] = new_thumb
                cv = await get_cv_detection(blink, name)
                announcement = build_announcement(name, cv)
                print(f"Motion on {name}: {cv}", flush=True)
                speak(announcement)

# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    print("Connecting to Blink...")
    blink = await setup_blink()
    await watch(blink)

if __name__ == "__main__":
    asyncio.run(main())
