"""
pipeline.py
Orchestrates the detection steps for each frame.
Runs face recognition every N frames (slow), gesture every frame (fast).
"""

import time
import threading
from . import events as ev_bus
from .face_recog import FaceRecognizer
from .emotion    import EmotionDetector
from .gesture    import GestureDetector


class Pipeline:
    def __init__(self, face_interval: int = 5):
        """
        face_interval: run face recognition every N frames.
        Gesture runs every frame. Face+emotion run on a thread to avoid blocking.
        """
        self.face_interval = face_interval
        self.recognizer    = FaceRecognizer()
        self.emotion       = EmotionDetector()
        self.gesture       = GestureDetector()

        self._frame_id      = 0
        self._last_faces    = []
        self._last_emotions = []
        self._face_lock     = threading.Lock()
        self._face_running  = False   # prevents concurrent dlib calls

    def _run_face_recognition(self, frame):
        """Runs in background thread — updates cached results. Only one at a time."""
        try:
            faces    = self.recognizer.detect_and_recognize(frame)
            bboxes   = [f["bbox"] for f in faces]
            emotions = self.emotion.analyze(frame, bboxes)
            with self._face_lock:
                self._last_faces    = faces
                self._last_emotions = emotions
        finally:
            self._face_running = False

    def process(self, frame) -> tuple:
        """
        Process a single frame.
        Returns: (event_dict, annotated_frame)
        """
        self._frame_id += 1

        # Kick off face recognition in background every N frames,
        # but only if the previous run has finished (dlib is not thread-safe)
        if self._frame_id % self.face_interval == 1 and not self._face_running:
            self._face_running = True
            t = threading.Thread(
                target=self._run_face_recognition,
                args=(frame.copy(),),
                daemon=True,
            )
            t.start()

        # Gesture detection — every frame, fast
        gestures, annotated = self.gesture.detect(frame)

        # Get latest face results (cached from background thread)
        with self._face_lock:
            faces   = list(self._last_faces)
            emotions = list(self._last_emotions)

        event = ev_bus.build_event(
            frame_id = self._frame_id,
            faces    = faces,
            gestures = gestures,
            emotions = emotions,
            meta     = {},  # filled in by main.py from camera.get_meta()
        )

        return event, annotated

    def close(self):
        self.gesture.close()
