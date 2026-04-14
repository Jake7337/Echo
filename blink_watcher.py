"""
blink_watcher.py
Watches Blink cameras for motion and has Echo announce it out loud.
Run this alongside echo_voice.py or on its own.
"""

import io
import json
import os
import time
import wave
import subprocess
import asyncio
from datetime import datetime
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from piper import PiperVoice

CREDS_FILE   = os.path.join(os.path.dirname(__file__), "blink_creds.json")
PIPER_MODEL  = os.path.join(os.path.dirname(__file__), "en_US-lessac-medium.onnx")
FFPLAY       = r"C:\Users\jrsrl\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffplay.exe"
POLL_SECONDS = 30  # how often to check for new motion

# ── Voice ──────────────────────────────────────────────────────────────────────

def speak(text: str, voice: PiperVoice):
    print(f"Echo: {text}")
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        voice.synthesize_wav(text, wav)
    buf.seek(0)
    proc = subprocess.Popen(
        [FFPLAY, "-nodisp", "-autoexit", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.communicate(input=buf.read())

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

async def watch(blink: Blink, voice: PiperVoice):
    seen = set()

    print("Echo is watching the cameras...\n")

    # Seed thumbnails so we only announce changes, not startup state
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
                print(f"Motion on {name}", flush=True)
                speak(f"Motion detected on {name}.", voice)

# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    print("Loading voice...")
    voice = PiperVoice.load(PIPER_MODEL)

    print("Connecting to Blink...")
    blink = await setup_blink()

    await watch(blink, voice)

if __name__ == "__main__":
    asyncio.run(main())
