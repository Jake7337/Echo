"""
pipeline.py
Hardened pipeline with a single persistent face-recognition worker thread.

Architecture:
  - capture_loop (main thread) pushes frames into _face_queue every N frames
  - _face_worker_loop (one dedicated thread) pulls and runs dlib — no concurrency
  - Watchdog resets _face_running if a job takes too long
  - All errors are caught and logged; never propagate to kill the process
"""

import logging
import queue
import threading
import time

from . import events as ev_bus
from .face_recog import FaceRecognizer
from .emotion    import EmotionDetector
from .gesture    import GestureDetector

log = logging.getLogger("webcam_intel.pipeline")

FACE_TIMEOUT_SEC = 8.0   # job stuck longer than this → watchdog resets flag


class Pipeline:
    def __init__(self, face_interval: int = 5):
        self.face_interval = face_interval

        self.recognizer = FaceRecognizer()
        self.emotion    = EmotionDetector()
        self.gesture    = GestureDetector()

        self._frame_id       = 0
        self._last_faces     = []
        self._last_emotions  = []
        self._result_lock    = threading.Lock()

        self._face_running    = False
        self._last_face_start = 0.0
        self._face_queue      = queue.Queue(maxsize=2)
        self._worker_running  = True

        self._face_thread = threading.Thread(
            target=self._face_worker_loop,
            name="FaceWorker",
            daemon=True,
        )
        self._face_thread.start()
        log.info("Pipeline ready — FaceWorker thread started")

    # ── Face worker (single thread, no concurrent dlib) ───────────────────────

    def _face_worker_loop(self):
        log.info("FaceWorker: running")
        while self._worker_running:
            try:
                frame = self._face_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            self._face_running    = True
            self._last_face_start = time.time()
            try:
                faces    = self.recognizer.detect_and_recognize(frame)
                bboxes   = [f["bbox"] for f in faces]
                emotions = self.emotion.analyze(frame, bboxes)
                with self._result_lock:
                    self._last_faces    = faces
                    self._last_emotions = emotions
                log.debug("FaceWorker: %d face(s) detected", len(faces))
            except Exception as e:
                log.exception("FaceWorker unexpected error: %s", e)
            finally:
                self._face_running = False
                try:
                    self._face_queue.task_done()
                except ValueError:
                    pass

        log.info("FaceWorker: stopped")

    # ── Watchdog ──────────────────────────────────────────────────────────────

    def _check_watchdog(self):
        if self._face_running:
            elapsed = time.time() - self._last_face_start
            if elapsed > FACE_TIMEOUT_SEC:
                log.warning("FaceWorker watchdog: job took %.1fs — resetting", elapsed)
                self._face_running = False
                # drain queue so next frame starts fresh
                while not self._face_queue.empty():
                    try:
                        self._face_queue.get_nowait()
                        self._face_queue.task_done()
                    except (queue.Empty, ValueError):
                        break

    # ── Main process entry ────────────────────────────────────────────────────

    def process(self, frame) -> tuple:
        """
        Process one frame from the capture loop.
        Returns (event_dict, annotated_frame).
        """
        if frame is None or frame.size == 0:
            log.debug("process: skipping invalid frame")
            with self._result_lock:
                faces    = list(self._last_faces)
                emotions = list(self._last_emotions)
            event = ev_bus.build_event(self._frame_id, faces, [], emotions, {})
            return event, frame

        self._frame_id += 1
        self._check_watchdog()

        # Push to face worker every N frames (non-blocking — drop if busy)
        if self._frame_id % self.face_interval == 1 and not self._face_running:
            try:
                self._face_queue.put_nowait(frame.copy())
            except queue.Full:
                log.debug("Face queue full — skipping frame %d", self._frame_id)

        # Gesture detection — every frame, fast
        try:
            gestures, annotated = self.gesture.detect(frame)
        except Exception as e:
            log.exception("Gesture detection error: %s", e)
            gestures, annotated = [], frame.copy()

        # Read latest face results (set by worker thread)
        with self._result_lock:
            faces    = list(self._last_faces)
            emotions = list(self._last_emotions)

        event = ev_bus.build_event(
            frame_id = self._frame_id,
            faces    = faces,
            gestures = gestures,
            emotions = emotions,
            meta     = {},
        )
        return event, annotated

    def close(self):
        self._worker_running = False
        try:
            self.gesture.close()
        except Exception:
            pass
        log.info("Pipeline closed")
