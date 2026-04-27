"""
camera.py
Webcam capture loop for Echo's Webcam Intelligence Module.
Opens the C920s, yields frames via a generator.
"""

import cv2
import time
import threading


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, fps: int = 15):
        self.index  = index
        self.width  = width
        self.height = height
        self.fps    = fps
        self._cap   = None
        self._frame = None
        self._lock  = threading.Lock()
        self._running = False
        self._thread  = None

    def start(self):
        self._cap = cv2.VideoCapture(self.index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS,          self.fps)

        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open camera at index {self.index}")

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_f = self._cap.get(cv2.CAP_PROP_FPS)
        print(f"[camera] Opened: {actual_w}x{actual_h} @ {actual_f:.0f}fps", flush=True)

        self._running = True
        self._thread  = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        interval = 1.0 / self.fps
        while self._running:
            t0 = time.time()
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
            elapsed = time.time() - t0
            sleep   = max(0, interval - elapsed)
            if sleep:
                time.sleep(sleep)

    def read(self):
        """Return the latest frame, or None if not ready."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def get_meta(self) -> dict:
        if not self._cap:
            return {}
        return {
            "frame_width":  int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "frame_height": int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps":          self._cap.get(cv2.CAP_PROP_FPS),
        }

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap:
            self._cap.release()
        print("[camera] Stopped.", flush=True)
