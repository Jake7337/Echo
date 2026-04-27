"""
gesture.py
Hand gesture detection using MediaPipe Hands.
Detects: thumbs_up, thumbs_down, open_palm, fist, wave.

MediaPipe landmark indices:
  Wrist=0, Thumb: 1-4, Index: 5-8, Middle: 9-12, Ring: 13-16, Pinky: 17-20
  TIP landmarks: thumb=4, index=8, middle=12, ring=16, pinky=20
  PIP landmarks: thumb=3, index=7, middle=11, ring=15, pinky=19
  MCP (base): index=5, middle=9, ring=13, pinky=17

In normalized coords: y=0 is top, y=1 is bottom.
So smaller y = higher in frame (toward ceiling).

Current state: stub if mediapipe.solutions is unavailable (Python 3.12+ compatibility issue).
Will auto-activate once a compatible mediapipe build is available.
"""

import numpy as np
from collections import deque

# Try to load MediaPipe — not available on all Python versions
_MP_AVAILABLE = False
try:
    import mediapipe as mp
    _ = mp.solutions.hands   # will AttributeError if version doesn't support it
    _MP_AVAILABLE = True
    print("[gesture] MediaPipe Hands loaded", flush=True)
except Exception as e:
    print(f"[gesture] MediaPipe unavailable ({e}) — gesture detection disabled. "
          f"Fix: pip install mediapipe==0.10.14 (requires Python <=3.12)", flush=True)


class GestureDetector:
    def __init__(self):
        if _MP_AVAILABLE:
            import mediapipe as mp
            self.mp_hands = mp.solutions.hands
            self.mp_draw  = mp.solutions.drawing_utils
            self.hands    = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )
        else:
            self.hands = None

        # Wave detection: track wrist x-position history per hand
        self._wave_history = deque(maxlen=20)
        self._wave_dirs    = deque(maxlen=10)

    def _finger_extended(self, lm, tip: int, pip: int) -> bool:
        return lm[tip].y < lm[pip].y

    def _thumb_up(self, lm) -> bool:
        thumb_up   = lm[4].y < lm[5].y
        idx_curled = lm[8].y  > lm[7].y
        mid_curled = lm[12].y > lm[11].y
        rng_curled = lm[16].y > lm[15].y
        pnk_curled = lm[20].y > lm[19].y
        return thumb_up and idx_curled and mid_curled and rng_curled and pnk_curled

    def _thumb_down(self, lm) -> bool:
        thumb_down = lm[4].y > lm[0].y
        idx_curled = lm[8].y  > lm[7].y
        mid_curled = lm[12].y > lm[11].y
        rng_curled = lm[16].y > lm[15].y
        pnk_curled = lm[20].y > lm[19].y
        return thumb_down and idx_curled and mid_curled and rng_curled and pnk_curled

    def _open_palm(self, lm) -> bool:
        return (
            self._finger_extended(lm, 8,  7)  and
            self._finger_extended(lm, 12, 11) and
            self._finger_extended(lm, 16, 15) and
            self._finger_extended(lm, 20, 19)
        )

    def _fist(self, lm) -> bool:
        return (
            lm[4].y  > lm[3].y  and
            lm[8].y  > lm[7].y  and
            lm[12].y > lm[11].y and
            lm[16].y > lm[15].y and
            lm[20].y > lm[19].y
        )

    def _check_wave(self, wrist_x: float) -> bool:
        self._wave_history.append(wrist_x)
        if len(self._wave_history) < 6:
            return False
        hist = list(self._wave_history)
        dirs = []
        for i in range(1, len(hist)):
            diff = hist[i] - hist[i-1]
            if abs(diff) > 0.02:
                dirs.append(1 if diff > 0 else -1)
        if len(dirs) < 4:
            return False
        reversals = sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i-1])
        return reversals >= 3

    def classify(self, lm) -> tuple:
        if self._thumb_up(lm):
            return "thumbs_up", 0.85
        if self._thumb_down(lm):
            return "thumbs_down", 0.85
        if self._open_palm(lm):
            return "open_palm", 0.80
        if self._fist(lm):
            return "fist", 0.75
        if self._check_wave(lm[0].x):
            return "wave", 0.70
        return "none", 0.0

    def detect(self, frame) -> tuple:
        """
        Run hand detection on frame.
        Returns: (gestures_list, annotated_frame)
        """
        import cv2
        out = frame.copy()

        if not _MP_AVAILABLE or self.hands is None:
            return [], out

        rgb     = frame[:, :, ::-1]
        results = self.hands.process(rgb)
        gestures = []

        if not results.multi_hand_landmarks:
            return gestures, out

        fh, fw = frame.shape[:2]

        for hand_lm in results.multi_hand_landmarks:
            self.mp_draw.draw_landmarks(
                out, hand_lm, self.mp_hands.HAND_CONNECTIONS,
                self.mp_draw.DrawingSpec(color=(0, 200, 80),  thickness=2, circle_radius=3),
                self.mp_draw.DrawingSpec(color=(0, 100, 255), thickness=2),
            )

            lm = hand_lm.landmark
            xs = [l.x for l in lm]
            ys = [l.y for l in lm]
            x1, y1 = int(min(xs) * fw), int(min(ys) * fh)
            x2, y2 = int(max(xs) * fw), int(max(ys) * fh)
            bbox   = [x1, y1, x2 - x1, y2 - y1]

            gesture, conf = self.classify(lm)
            if gesture != "none":
                gestures.append({
                    "type":       gesture,
                    "confidence": conf,
                    "bbox":       bbox,
                })

        return gestures, out

    def close(self):
        if self.hands:
            self.hands.close()
