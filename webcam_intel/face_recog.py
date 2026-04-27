"""
face_recog.py
Face detection and recognition using the face_recognition library (dlib backend).

All dlib calls are wrapped in try/except — a crash in native code returns an
empty result instead of killing the worker thread.

Encodings load in a background thread so startup is instant.
"""

import os
import logging
import threading
import cv2
import face_recognition
import numpy as np
from pathlib import Path

log = logging.getLogger("webcam_intel.face_recog")

KNOWN_FACES_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent / "known_faces"
TOLERANCE       = 0.52

# Global lock — dlib's C code is NOT thread-safe.
# Every call into face_recognition must hold this lock.
_DLIB_LOCK = threading.Lock()


class FaceRecognizer:
    def __init__(self):
        self.known_encodings = []
        self.known_names     = []
        self._enc_lock       = threading.Lock()
        self._ready          = False
        t = threading.Thread(target=self._load_known_faces, daemon=True, name="FaceEncoderLoader")
        t.start()

    # ── Startup encoding load (background) ───────────────────────────────────

    def _load_known_faces(self):
        if not KNOWN_FACES_DIR.exists():
            log.warning("known_faces/ not found at %s", KNOWN_FACES_DIR)
            self._ready = True
            return

        encodings, names = [], []
        loaded = 0

        for entry in sorted(KNOWN_FACES_DIR.iterdir()):
            if not entry.is_dir():
                continue
            name  = entry.name
            files = list(entry.glob("*.jpg")) + list(entry.glob("*.jpeg")) + list(entry.glob("*.png"))
            for img_path in files:
                try:
                    img = face_recognition.load_image_file(str(img_path))
                    with _DLIB_LOCK:
                        encs = face_recognition.face_encodings(img)
                    if encs:
                        encodings.append(encs[0])
                        names.append(name)
                        loaded += 1
                except Exception as e:
                    log.warning("Skipped %s: %s", img_path.name, e)

        with self._enc_lock:
            self.known_encodings = encodings
            self.known_names     = names
            self._ready          = True

        log.info("Loaded %d encodings for %d people: %s",
                 loaded, len(set(names)), sorted(set(names)))
        print(f"[face_recog] Loaded {loaded} encodings — "
              f"{sorted(set(names))}", flush=True)

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect_and_recognize(self, frame) -> list:
        """
        Detect all faces and identify them.
        Returns list of {id, confidence, bbox} or [] on any failure.
        """
        # Guard: never pass bad frames into dlib
        if frame is None or frame.size == 0:
            log.debug("detect_and_recognize: invalid frame, skipping")
            return []

        # ── Step 1: locate faces on half-res for speed ────────────────────────
        try:
            small  = frame[::2, ::2]
            rgb_sm = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            with _DLIB_LOCK:
                locations = face_recognition.face_locations(rgb_sm, model="hog")
        except Exception as e:
            log.exception("face_locations failed: %s", e)
            return []

        if not locations:
            return []

        # Scale back up to full-res coords
        locations_full = [(t*2, r*2, b*2, l*2) for (t, r, b, l) in locations]

        # ── Step 2: compute encodings on full-res ─────────────────────────────
        try:
            rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with _DLIB_LOCK:
                encodings = face_recognition.face_encodings(rgb_full, locations_full)
        except Exception as e:
            log.exception("face_encodings failed: %s", e)
            return []

        # Snapshot of known encodings (thread-safe read)
        with self._enc_lock:
            known_enc   = list(self.known_encodings)
            known_names = list(self.known_names)

        # ── Step 3: match each encoding ───────────────────────────────────────
        results = []
        for (top, right, bottom, left), enc in zip(locations_full, encodings):
            name       = "unknown"
            confidence = 0.0
            try:
                if known_enc:
                    with _DLIB_LOCK:
                        distances = face_recognition.face_distance(known_enc, enc)
                    best_idx  = int(np.argmin(distances))
                    best_dist = float(distances[best_idx])
                    if best_dist <= TOLERANCE:
                        name       = known_names[best_idx]
                        confidence = round(1.0 - best_dist, 3)
            except Exception as e:
                log.exception("face_distance failed: %s", e)

            results.append({
                "id":         name,
                "confidence": confidence,
                "bbox":       [left, top, right - left, bottom - top],
            })

        return results
