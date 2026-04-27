"""
camera.py
Self-healing webcam capture for Echo's Webcam Intelligence Module.
Reopens the camera automatically on repeated read failures.
"""

import cv2
import time
import logging
import threading

log = logging.getLogger("webcam_intel.camera")

MAX_FAILURES  = 10     # consecutive bad frames before reopen attempt
REOPEN_DELAY  = 3.0    # seconds between reopen retries


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, fps: int = 15):
        self.index   = index
        self.width   = width
        self.height  = height
        self.fps     = fps
        self._cap    = None
        self._frame  = None
        self._lock   = threading.Lock()
        self._running = False
        self._thread  = None

    # ── Open / close ──────────────────────────────────────────────────────────

    def _open_camera(self):
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = cv2.VideoCapture(self.index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS,          self.fps)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open camera at index {self.index}")
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        f = self._cap.get(cv2.CAP_PROP_FPS)
        log.info("Camera opened: %dx%d @ %.0ffps", w, h, f)
        print(f"[camera] Opened: {w}x{h} @ {f:.0f}fps", flush=True)

    def start(self):
        self._open_camera()
        self._running = True
        self._thread  = threading.Thread(target=self._capture_loop, daemon=True, name="CameraCapture")
        self._thread.start()

    # ── Capture loop ──────────────────────────────────────────────────────────

    def _capture_loop(self):
        interval = 1.0 / self.fps
        failures = 0

        while self._running:
            t0 = time.time()

            try:
                ret, frame = self._cap.read()
            except Exception as e:
                log.warning("cap.read() exception: %s", e)
                ret, frame = False, None

            if ret and frame is not None and frame.size > 0:
                failures = 0
                with self._lock:
                    self._frame = frame
            else:
                failures += 1
                log.debug("Bad frame (%d consecutive)", failures)

                if failures >= MAX_FAILURES:
                    log.warning("Camera: %d consecutive failures — reopening...", failures)
                    print(f"[camera] {failures} failures — reopening camera...", flush=True)
                    while self._running:
                        try:
                            self._open_camera()
                            failures = 0
                            break
                        except Exception as e:
                            log.error("Reopen failed: %s — retry in %.0fs", e, REOPEN_DELAY)
                            time.sleep(REOPEN_DELAY)

            elapsed = time.time() - t0
            sleep   = max(0.0, interval - elapsed)
            if sleep:
                time.sleep(sleep)

    # ── Public API ────────────────────────────────────────────────────────────

    def read(self):
        """Return latest frame copy, or None if not yet available."""
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
            try:
                self._cap.release()
            except Exception:
                pass
        log.info("Camera stopped")
        print("[camera] Stopped.", flush=True)
