"""
echo_identify.py
Snap the 'Echo' Blink camera and identify who's in frame.

Setup:
  1. pip install cmake dlib face_recognition
     (if dlib fails on Windows: pip install deepface instead, see fallback below)
  2. Drop reference photos into known_faces/ folder — one photo per person.
     Name the file after the person: jake.jpg, rachael.jpg, etc.
  3. Run once to verify: python echo_identify.py

Called by echo_server.py /api/identify endpoint.
"""

import os
import io
import json
import asyncio
import time

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR  = os.path.join(BASE_DIR, "known_faces")
SESSION_FILE     = os.path.join(BASE_DIR, "blink_session.json")
CAMERA_NAME      = "Echo"

# ── Load known face encodings once at import ──────────────────────────────────

_known_encodings = {}   # name -> encoding

def _load_known_faces():
    global _known_encodings
    if not os.path.exists(KNOWN_FACES_DIR):
        print("[identify] known_faces/ not found — no faces enrolled")
        return
    try:
        import face_recognition
    except ImportError:
        print("[identify] face_recognition not installed — run: pip install cmake dlib face_recognition")
        return

    for fname in os.listdir(KNOWN_FACES_DIR):
        if fname.lower().endswith((".jpg", ".jpeg", ".png")):
            name = os.path.splitext(fname)[0]
            path = os.path.join(KNOWN_FACES_DIR, fname)
            try:
                img  = face_recognition.load_image_file(path)
                encs = face_recognition.face_encodings(img)
                if encs:
                    _known_encodings[name] = encs[0]
                    print(f"[identify] Enrolled: {name}")
                else:
                    print(f"[identify] No face found in {fname} — skipping")
            except Exception as e:
                print(f"[identify] Could not load {fname}: {e}")

    print(f"[identify] {len(_known_encodings)} face(s) enrolled: {list(_known_encodings.keys())}")

_load_known_faces()


# ── Blink snapshot ────────────────────────────────────────────────────────────

async def _snap_blink() -> bytes | None:
    """Connect to Blink via saved session, snap Echo camera, return image bytes."""
    from blinkpy.blinkpy import Blink
    from blinkpy.auth import Auth

    if not os.path.exists(SESSION_FILE):
        print("[identify] No blink_session.json found")
        return None

    with open(SESSION_FILE) as f:
        saved = json.load(f)

    blink = Blink()
    auth  = Auth(saved, no_prompt=True)
    blink.auth = auth

    try:
        await blink.start()
    except Exception as e:
        print(f"[identify] Blink connect failed: {e}")
        return None

    blink.last_refresh = int(time.time())

    cam = blink.cameras.get(CAMERA_NAME)
    if not cam:
        print(f"[identify] Camera '{CAMERA_NAME}' not found. Available: {list(blink.cameras.keys())}")
        return None

    # Trigger a fresh snapshot
    try:
        await cam.snap_picture()
        await asyncio.sleep(3)   # give camera time to process
        await blink.refresh()
    except Exception as e:
        print(f"[identify] Snap failed: {e}")

    thumb_url = cam.thumbnail
    if not thumb_url:
        return None

    try:
        resp = blink.auth.session.get(thumb_url, timeout=10)
        return resp.content
    except Exception as e:
        print(f"[identify] Thumbnail download failed: {e}")
        return None


# ── Face recognition ──────────────────────────────────────────────────────────

def _recognize(img_bytes: bytes) -> str:
    """Compare image bytes against known faces. Returns name or 'unknown'."""
    try:
        import face_recognition
    except ImportError:
        return "unknown"

    if not _known_encodings:
        return "someone"   # camera worked, just no faces enrolled yet

    try:
        img  = face_recognition.load_image_file(io.BytesIO(img_bytes))
        encs = face_recognition.face_encodings(img)

        if not encs:
            return "no_face"

        unknown_enc = encs[0]
        for name, known_enc in _known_encodings.items():
            match = face_recognition.compare_faces([known_enc], unknown_enc, tolerance=0.55)
            if match[0]:
                return name

        return "unknown"
    except Exception as e:
        print(f"[identify] Recognition error: {e}")
        return "unknown"


# ── Public interface ──────────────────────────────────────────────────────────

def identify_person(timeout: int = 12) -> str:
    """
    Snap Echo camera and return who's in frame.
    Returns: name string, 'unknown', 'no_face', or 'error'
    Synchronous — handles async internally.
    """
    try:
        loop = asyncio.new_event_loop()
        img_bytes = loop.run_until_complete(
            asyncio.wait_for(_snap_blink(), timeout=timeout - 2)
        )
        loop.close()
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as e:
        print(f"[identify] Snap error: {e}")
        return "error"

    if not img_bytes:
        return "unknown"

    return _recognize(img_bytes)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing identify...")
    result = identify_person()
    print(f"Result: {result}")
