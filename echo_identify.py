"""
echo_identify.py
Snap the 'Echo' Blink camera and identify who's in frame.

Setup:
  1. pip install opencv-python opencv-contrib-python
  2. Drop reference photos into known_faces/ — one per person, named after them: jake.jpg
  3. Test: python echo_identify.py

Called by echo_server.py /api/identify endpoint.
"""

import os
import io
import json
import asyncio
import time
import tempfile
import numpy as np

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
SESSION_FILE    = os.path.join(BASE_DIR, "blink_session.json")
CAMERA_NAME     = "Echo"

# Haar cascade for face detection (bundled with opencv)
_cascade = None
_recognizer = None
_label_map  = {}   # int label -> name

def _get_cascade():
    global _cascade
    if _cascade is None:
        import cv2
        _cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _cascade

def _load_known_faces():
    """Build and train the LBPH face recognizer from known_faces/ images."""
    global _recognizer, _label_map
    try:
        import cv2
    except ImportError:
        print("[identify] opencv not installed — run: pip install opencv-python opencv-contrib-python")
        return

    if not os.path.exists(KNOWN_FACES_DIR):
        return

    import re
    cascade       = _get_cascade()
    faces         = []
    labels        = []
    name_to_label = {}   # name -> int label
    label_idx     = 0

    for fname in sorted(os.listdir(KNOWN_FACES_DIR)):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        if fname == "last_snap.jpg":
            continue  # debug snapshot, not a reference face
        # Strip trailing _N suffix — jake_1.jpg, jake_2.jpg all map to "jake"
        base = os.path.splitext(fname)[0]
        name = re.sub(r"_\d+$", "", base)

        # Assign or reuse label for this name
        if name not in name_to_label:
            name_to_label[name] = label_idx
            _label_map[label_idx] = name
            label_idx += 1

        path = os.path.join(KNOWN_FACES_DIR, fname)
        img  = cv2.imread(path)
        if img is None:
            print(f"[identify] Could not read {fname}")
            continue
        gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        detected = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(detected) == 0:
            print(f"[identify] No face detected in {fname} — try a clearer photo")
            continue
        x, y, w, h = detected[0]
        face_roi = gray[y:y+h, x:x+w]
        face_roi = cv2.resize(face_roi, (200, 200))
        faces.append(face_roi)
        labels.append(name_to_label[name])
        print(f"[identify] Enrolled: {fname} → {name}")

    if faces:
        _recognizer = cv2.face.LBPHFaceRecognizer_create()
        _recognizer.train(faces, np.array(labels))
        print(f"[identify] Recognizer trained on {len(faces)} face(s): {list(_label_map.values())}")
    else:
        print("[identify] No faces enrolled — add photos to known_faces/")

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

    # Refresh to get current camera state — no snap needed, just grab what's visible now
    try:
        await blink.refresh()
    except Exception as e:
        print(f"[identify] Refresh warning: {e}")

    thumb_url = cam.thumbnail
    print(f"[identify] Thumbnail URL: {thumb_url}")

    if not thumb_url:
        print("[identify] No thumbnail URL")
        return None

    # Ensure URL is absolute
    if thumb_url.startswith("/"):
        thumb_url = f"https://rest-prod.immedia-semi.com{thumb_url}"

    try:
        headers = blink.auth.header  # {"TOKEN_AUTH": "<token>"}
        async with blink.auth.session.get(thumb_url, headers=headers) as resp:
            print(f"[identify] HTTP {resp.status}")
            data = await resp.read()
            print(f"[identify] Downloaded {len(data)} bytes")
            return data
    except Exception as e:
        print(f"[identify] Thumbnail download failed: {e}")
        return None


# ── Face recognition ──────────────────────────────────────────────────────────

def _recognize(img_bytes: bytes) -> str:
    """Detect and recognize face in image bytes using OpenCV LBPH."""
    try:
        import cv2
    except ImportError:
        return "unknown"

    if _recognizer is None or not _label_map:
        return "someone"

    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img       = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        return "unknown"

    # Save snapshot for debugging — check known_faces/last_snap.jpg to see what camera grabbed
    debug_path = os.path.join(BASE_DIR, "known_faces", "last_snap.jpg")
    cv2.imwrite(debug_path, img)
    print(f"[identify] Snapshot saved to {debug_path}")

    gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade  = _get_cascade()
    # Looser params: scaleFactor 1.05 catches more angles, minNeighbors 3 is less strict
    detected = cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(30, 30))

    if len(detected) == 0:
        print("[identify] No face detected in snapshot")
        return "no_face"

    x, y, w, h   = detected[0]
    face_roi     = gray[y:y+h, x:x+w]
    face_roi     = cv2.resize(face_roi, (200, 200))

    label, confidence = _recognizer.predict(face_roi)
    print(f"[identify] Prediction: label={label} confidence={confidence:.1f}")

    # Lower confidence = better match in LBPH. Blink thumbnails are compressed so threshold is looser.
    if confidence < 140:
        return _label_map.get(label, "unknown")
    return "unknown"


# ── Public interface ──────────────────────────────────────────────────────────

def identify_person(timeout: int = 25) -> str:
    """
    Snap Echo camera and return who's in frame.
    Returns: name string, 'unknown', 'no_face', 'timeout', or 'error'
    Synchronous — handles async internally.
    """
    try:
        loop = asyncio.new_event_loop()
        img_bytes = loop.run_until_complete(
            asyncio.wait_for(_snap_blink(), timeout=timeout - 3)
        )
        loop.close()
    except asyncio.TimeoutError:
        print("[identify] Timed out waiting for snap")
        return "timeout"
    except Exception as e:
        print(f"[identify] Snap error: {e}")
        return "error"

    if not img_bytes:
        return "unknown"

    return _recognize(img_bytes)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing identify — sit in front of the Echo camera...")
    result = identify_person()
    print(f"Result: {result}")
