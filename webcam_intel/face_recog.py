"""
face_recog.py
Face detection and recognition using the face_recognition library.
Loads known faces from Echo's known_faces/ directory automatically.
"""

import os
import threading
import face_recognition
import numpy as np
from pathlib import Path

KNOWN_FACES_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent / "known_faces"
TOLERANCE       = 0.52   # lower = stricter match (0.6 is library default)


class FaceRecognizer:
    def __init__(self):
        self.known_encodings = []  # list of np arrays
        self.known_names     = []  # parallel list of names
        self._enc_lock       = threading.Lock()
        self._ready          = False
        # Load in background so Flask starts immediately
        t = threading.Thread(target=self._load_known_faces, daemon=True)
        t.start()

    def _load_known_faces(self):
        if not KNOWN_FACES_DIR.exists():
            print(f"[face_recog] known_faces/ not found at {KNOWN_FACES_DIR}", flush=True)
            self._ready = True
            return

        encodings, names = [], []
        loaded = 0
        for entry in sorted(KNOWN_FACES_DIR.iterdir()):
            if entry.is_dir():
                name  = entry.name
                files = list(entry.glob("*.jpg")) + list(entry.glob("*.jpeg")) + list(entry.glob("*.png"))
                for img_path in files:
                    try:
                        img  = face_recognition.load_image_file(str(img_path))
                        encs = face_recognition.face_encodings(img)
                        if encs:
                            encodings.append(encs[0])
                            names.append(name)
                            loaded += 1
                    except Exception as e:
                        print(f"[face_recog] Skipped {img_path.name}: {e}", flush=True)

        with self._enc_lock:
            self.known_encodings = encodings
            self.known_names     = names
            self._ready          = True

        print(f"[face_recog] Loaded {loaded} encodings for {len(set(names))} people: "
              f"{sorted(set(names))}", flush=True)

    def detect_and_recognize(self, frame) -> list:
        """
        Detect all faces in frame and identify them.
        Returns list of dicts: {id, confidence, bbox}
        bbox is (x, y, w, h) in pixel coords.
        """
        # Scale down for speed — detection on half-size, recognition on full
        small  = frame[::2, ::2]   # half resolution
        rgb_sm = small[:, :, ::-1]  # BGR -> RGB

        locations = face_recognition.face_locations(rgb_sm, model="hog")
        if not locations:
            return []

        # Scale locations back up
        locations_full = [(t*2, r*2, b*2, l*2) for (t, r, b, l) in locations]

        rgb_full  = frame[:, :, ::-1]
        encodings = face_recognition.face_encodings(rgb_full, locations_full)

        with self._enc_lock:
            known_enc  = list(self.known_encodings)
            known_names = list(self.known_names)

        results = []
        for (top, right, bottom, left), enc in zip(locations_full, encodings):
            name       = "unknown"
            confidence = 0.0

            if known_enc:
                distances = face_recognition.face_distance(known_enc, enc)
                best_idx  = int(np.argmin(distances))
                best_dist = float(distances[best_idx])

                if best_dist <= TOLERANCE:
                    name = known_names[best_idx]
                    # Convert distance to a 0-1 confidence score
                    confidence = round(1.0 - best_dist, 3)

            x = left
            y = top
            w = right  - left
            h = bottom - top

            results.append({
                "id":         name,
                "confidence": confidence,
                "bbox":       [x, y, w, h],
            })

        return results
