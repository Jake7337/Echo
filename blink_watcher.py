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


async def watch(blink: Blink):
    from blinkpy import api as blink_api

    print("Echo is watching the cameras...\n")

    # Seed with current latest media ID so we only announce new events
    await blink.refresh()
    print(f"Watching {len(blink.cameras)} cameras...", flush=True)

    seen_ids: set = set()

    # Seed seen_ids with anything already in the last 5 minutes
    seed_data = await blink_api.request_videos(blink, time=time.time() - 300, page=0)
    if isinstance(seed_data, dict):
        for item in seed_data.get("media", []):
            seen_ids.add(item["id"])
    print(f"Seeded {len(seen_ids)} recent event IDs.", flush=True)

    while True:
        await asyncio.sleep(POLL_SECONDS)

        data = await blink_api.request_videos(blink, time=time.time() - POLL_SECONDS - 10, page=0)
        if not isinstance(data, dict):
            continue

        for item in data.get("media", []):
            item_id = item.get("id")
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            camera_name = item.get("device_name", "unknown camera")
            metadata_raw = item.get("metadata") or "{}"
            try:
                metadata = json.loads(metadata_raw)
            except Exception:
                metadata = {}

            cv_detection = metadata.get("cv_detection", [])
            announcement = build_announcement(camera_name, cv_detection)
            print(f"Motion on {camera_name}: {cv_detection}", flush=True)
            speak(announcement)

# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    print("Connecting to Blink...")
    blink = await setup_blink()
    await watch(blink)

if __name__ == "__main__":
    asyncio.run(main())
