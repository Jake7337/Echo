"""
blink_watcher.py
Echo's home awareness system.

Desk camera ("Echo"):
  Motion → identify face → speak greeting
  Unknown face → "Someone I don't recognize is at the desk"

Outdoor cameras:
  Smart filtering — cooldown, quiet hours, after-dark, object type, face recognition
"""

import sys
import json
import os
import time
import asyncio
import threading
import requests
from datetime import datetime
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE     = os.path.join(BASE_DIR, "blink_creds.json")
SESSION_FILE   = os.path.join(BASE_DIR, "blink_session.json")
CONFIG_FILE    = os.path.join(BASE_DIR, "awareness_config.json")
PI_SPEAK_URL   = "http://192.168.68.84:5100/speak"
IDENTIFY_URL   = "http://localhost:5050/api/identify"
POLL_SECONDS   = 30
DESK_CAMERA    = "Echo"
GREET_COOLDOWN = 3600  # seconds — don't re-greet same person within this window

# Greetings per known person — add names here as you enroll faces
GREETINGS = {
    "jake":    "Hey Jake — I see you.",
    "rachael": "Hey Rachael, what's up?",
    "judy":    "Hi Judy!",
    "brent":   "Hey Brent, good to see you.",
}

# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    defaults = {
        "quiet_hours": {"start": 23, "end": 7},
        "after_dark":  {"start": 21, "end": 6},
        "camera_cooldown_seconds": 300,
        "camera_enabled": {},
        "front_door_cameras": [],
        "vip_faces": [],
        "skip_objects": ["cat", "dog", "bird", "squirrel", "insect"],
    }
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        defaults.update(cfg)
    except Exception:
        pass
    return defaults

def _in_range(hour: int, start: int, end: int) -> bool:
    """True if hour is within [start, end) range, wrapping midnight."""
    if start >= end:  # wraps midnight (e.g. 23–7)
        return hour >= start or hour < end
    return start <= hour < end

def is_quiet_hours(cfg: dict) -> bool:
    qh = cfg.get("quiet_hours", {})
    if not qh.get("enabled", True):
        return False
    return _in_range(datetime.now().hour, qh.get("start", 23), qh.get("end", 7))

def is_after_dark(cfg: dict) -> bool:
    ad = cfg.get("after_dark", {})
    return _in_range(datetime.now().hour, ad.get("start", 21), ad.get("end", 6))

# ── Voice ─────────────────────────────────────────────────────────────────────

def speak(text: str):
    print(f"Echo: {text}", flush=True)
    try:
        requests.post(PI_SPEAK_URL, json={"text": text}, timeout=10)
    except Exception as e:
        print(f"[blink] speak failed: {e}", flush=True)

# ── Face identification ───────────────────────────────────────────────────────

def identify_person_async() -> list:
    """Call identify endpoint in a thread, return list of names."""
    result = [["unknown"]]
    def _run():
        try:
            r = requests.post(IDENTIFY_URL, timeout=35)
            result[0] = r.json().get("people", ["unknown"])
        except Exception as e:
            print(f"[identify] {e}", flush=True)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=35)
    return result[0]

# ── Desk camera ───────────────────────────────────────────────────────────────

def handle_desk_motion(last_greeted: dict):
    """Identify who's at the desk and greet them — once per hour per person."""
    print(f"[Echo camera] Motion — identifying...", flush=True)
    people = identify_person_async()
    print(f"[Echo camera] Identified: {people}", flush=True)

    SKIP = {"timeout", "error", "no_face", "unknown", "someone"}
    known = [p for p in people if p not in SKIP]

    if not known:
        if "no_face" not in people:
            speak("Someone's at the desk.")
        return

    now = time.time()
    for person in known:
        last = last_greeted.get(person, 0)
        if now - last < GREET_COOLDOWN:
            remaining = int((GREET_COOLDOWN - (now - last)) / 60)
            print(f"[Echo camera] {person} already greeted — {remaining}m until next greeting", flush=True)
            continue
        last_greeted[person] = now
        greeting = GREETINGS.get(person.lower(), f"Hey {person.capitalize()}!")
        speak(greeting)

# ── Outdoor cameras ───────────────────────────────────────────────────────────

def should_announce(camera_name: str, cv: list, description: str, last_announced: dict, cfg: dict) -> tuple[bool, str]:
    """
    Returns (should_announce, reason_or_text).
    Applies all filtering rules and returns announcement text or skip reason.
    """
    now       = time.time()
    overrides = cfg.get("camera_cooldown_overrides", {})
    cooldown  = overrides.get(camera_name, cfg.get("camera_cooldown_seconds", 300))
    after_dark = is_after_dark(cfg)
    quiet     = is_quiet_hours(cfg)
    front_door_cams = [c.lower() for c in cfg.get("front_door_cameras", [])]
    is_front  = camera_name.lower() in front_door_cams
    skip_objects = [o.lower() for o in cfg.get("skip_objects", [])]

    # Camera disabled
    cam_enabled = cfg.get("camera_enabled", {})
    if cam_enabled.get(camera_name, True) is False:
        return False, "camera disabled"

    # Cooldown
    if last_announced.get(camera_name, 0) + cooldown > now:
        elapsed = int(now - last_announced.get(camera_name, 0))
        return False, f"cooldown ({elapsed}s / {cooldown}s)"

    # Quiet hours — skip everything unless there's a person
    if quiet:
        has_person_desc = description and "person" in description.lower()
        has_person_cv   = cv and any("person" in o.lower() for o in cv)
        if not has_person_desc and not has_person_cv:
            return False, "quiet hours — no person"

    objects = [o.lower() for o in cv] if cv else []
    has_person  = any("person" in o for o in objects)
    has_vehicle = any(o in ("vehicle", "car", "truck") for o in objects)
    has_animal  = any(o in skip_objects for o in objects)

    # If Blink gave us a description, trust it and announce
    if description:
        return True, description

    # No description — use cv_detection if available
    if has_person:
        if is_front:
            return True, f"Someone at the {camera_name}."
        return True, f"Motion on {camera_name} — someone's out there."

    if has_vehicle:
        if after_dark or is_front:
            return True, f"A vehicle on {camera_name}."
        return False, "vehicle — daytime non-front skip"

    if has_animal:
        if after_dark:
            return True, f"Motion on {camera_name}."
        return False, "animal — daytime skip"

    # No cv data at all — announce generic motion (not quiet hours, not on cooldown)
    return True, f"Motion on {camera_name}."

# ── cv_detection lookup ───────────────────────────────────────────────────────

async def get_camera_event(blink, camera_name: str) -> tuple:
    """Returns (cv_detection list, blink_description string)."""
    from blinkpy import api as blink_api
    try:
        data = await blink_api.request_videos(blink, time=time.time() - 120, page=0)
        if not isinstance(data, dict):
            return [], ""
        for item in data.get("media", []):
            if item.get("device_name") == camera_name:
                try:
                    meta        = json.loads(item.get("metadata") or "{}")
                    cv          = meta.get("cv_detection", [])
                    description = (item.get("description", "") or
                                   meta.get("description", "") or "")
                    return cv, description.strip()
                except Exception:
                    return [], ""
    except Exception:
        pass
    return [], ""

# ── Blink setup ───────────────────────────────────────────────────────────────

async def setup_blink():
    with open(CREDS_FILE) as f:
        creds = json.load(f)

    blink = Blink(motion_interval=POLL_SECONDS)

    if os.path.exists(SESSION_FILE):
        print("Loading saved session...", flush=True)
        with open(SESSION_FILE) as f:
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

    blink.last_refresh = int(time.time())

    if blink.urls:
        await blink.save(SESSION_FILE)

    for name, sync in blink.sync.items():
        if not sync.arm:
            print(f"Arming {name}...", flush=True)
            await sync.async_arm(True)

    return blink

# ── Main watch loop ───────────────────────────────────────────────────────────

async def watch(blink: Blink):
    print("Echo awareness system active.\n", flush=True)
    await blink.refresh()
    last_thumbnails  = {name: cam.thumbnail for name, cam in blink.cameras.items()}
    last_announced   = {}
    last_desk_greet  = 0     # cooldown for snap loop prevention
    last_greeted     = {}    # person -> timestamp, prevents re-greeting same person

    cam_list = list(blink.cameras.keys())
    print(f"Watching {len(cam_list)} cameras: {cam_list}", flush=True)

    while True:
        await asyncio.sleep(POLL_SECONDS)
        await blink.refresh()
        cfg = load_config()

        for name, camera in blink.cameras.items():
            new_thumb = camera.thumbnail
            if not new_thumb or new_thumb == last_thumbnails.get(name):
                continue

            last_thumbnails[name] = new_thumb
            print(f"[{name}] Motion detected", flush=True)

            if name == DESK_CAMERA:
                # Cooldown — snap updates thumbnail, would loop without this
                if time.time() - last_desk_greet < 60:
                    print(f"[Echo camera] Skipped — cooldown active", flush=True)
                    continue
                last_desk_greet = time.time()
                threading.Thread(target=handle_desk_motion, args=(last_greeted,), daemon=True).start()
                continue

            # Outdoor camera — cv_detection + filter
            cv, description = await get_camera_event(blink, name)
            print(f"[{name}] cv={cv} description={repr(description)}", flush=True)
            announce, text = should_announce(name, cv, description, last_announced, cfg)

            if announce:
                last_announced[name] = time.time()
                speak(text)
                print(f"[{name}] → announced: {text}", flush=True)
            else:
                print(f"[{name}] → skipped ({text})", flush=True)

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("Connecting to Blink...", flush=True)
    blink = await setup_blink()
    await watch(blink)

if __name__ == "__main__":
    asyncio.run(main())
