"""
echo_context.py
Echo's context fusion layer — Layer 4 of the Blink pipeline.

Tracks event history, household presence, camera baselines, and health.
Generates smart narrative announcements using LLM + context.

No GPU needed. Runs on llama3.1:8b right now.
"""

import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR     = Path(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_FILE = BASE_DIR / "cache" / "blink" / "echo_context.json"
HEALTH_FILE  = BASE_DIR / "cache" / "blink" / "camera_health.json"

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"

# What each camera watches — feeds into LLM narrative
CAMERA_LOCATIONS = {
    "Echo":          "desk camera inside the house",
    "Main door":     "main front door",
    "Front porch":   "front porch",
    "Back yard":     "back yard",
    "Back yard 2":   "back yard (second camera)",
    "Back of house": "back of the house",
    "Pole":          "pole camera at the edge of the property",
}

PRESENCE_TTL    = 4 * 3600   # person considered home for 4 hours after last seen
HISTORY_WINDOW  = 24 * 3600  # keep 24 hours of event history
ANOMALY_THRESH  = 5           # more than this many events/hour = unusual


class EchoContext:

    def __init__(self):
        self.event_history = []  # [{camera, timestamp, cv_detection, description}]
        self.household     = {}  # person -> last_seen timestamp
        self.camera_health = {}  # camera -> {battery, temp, signal, online, last_check}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            if CONTEXT_FILE.exists():
                data           = json.loads(CONTEXT_FILE.read_text())
                self.event_history = data.get("event_history", [])
                self.household     = data.get("household", {})
                cutoff             = time.time() - HISTORY_WINDOW
                self.event_history = [e for e in self.event_history if e["timestamp"] > cutoff]
        except Exception as e:
            print(f"[context] Load error: {e}", flush=True)

        try:
            if HEALTH_FILE.exists():
                self.camera_health = json.loads(HEALTH_FILE.read_text())
        except Exception:
            pass

    def _save(self):
        try:
            CONTEXT_FILE.write_text(json.dumps({
                "event_history": self.event_history[-500:],
                "household":     self.household,
                "saved_at":      time.time(),
            }, indent=2))
        except Exception as e:
            print(f"[context] Save error: {e}", flush=True)

    def _save_health(self):
        try:
            HEALTH_FILE.write_text(json.dumps(self.camera_health, indent=2))
        except Exception:
            pass

    # ── Event recording ───────────────────────────────────────────────────────

    def record_event(self, camera: str, cv_detection: list, description: str):
        self.event_history.append({
            "camera":       camera,
            "timestamp":    time.time(),
            "cv_detection": cv_detection or [],
            "description":  description or "",
        })
        cutoff             = time.time() - HISTORY_WINDOW
        self.event_history = [e for e in self.event_history if e["timestamp"] > cutoff]
        self._save()

    def record_person_seen(self, person: str):
        self.household[person.lower()] = time.time()
        self._save()
        print(f"[context] Household: {person} marked home", flush=True)

    # ── Camera health ─────────────────────────────────────────────────────────

    def update_camera_health(self, cameras: dict):
        """
        Pass in blink.cameras dict from the watch loop.
        Logs battery, temp, signal, online status.
        Warns on low battery or offline cameras.
        """
        now     = datetime.now().isoformat()
        alerts  = []

        for name, cam in cameras.items():
            try:
                battery = getattr(cam, "battery_voltage", None) or getattr(cam, "battery", None)
                temp    = getattr(cam, "temperature", None)
                signal  = getattr(cam, "wifi_strength", None)
                online  = getattr(cam, "online", True)

                prev    = self.camera_health.get(name, {})

                self.camera_health[name] = {
                    "battery":    battery,
                    "temp":       temp,
                    "signal":     signal,
                    "online":     online,
                    "last_check": now,
                }

                # Warn on low battery (Blink reports as voltage or percentage — check both)
                if battery is not None:
                    batt_val = float(battery)
                    if batt_val < 2.5 or (batt_val <= 10 and batt_val > 0):
                        alerts.append(f"{name} battery low ({battery})")

                # Warn if camera went offline
                if online is False and prev.get("online") is not False:
                    alerts.append(f"{name} camera is offline")

            except Exception as e:
                print(f"[context] Health check error on {name}: {e}", flush=True)

        self._save_health()

        for alert in alerts:
            print(f"[context] ALERT: {alert}", flush=True)

        return alerts  # caller can speak these

    # ── Query helpers ─────────────────────────────────────────────────────────

    def who_is_home(self) -> list:
        cutoff = time.time() - PRESENCE_TTL
        return [p for p, ts in self.household.items() if ts > cutoff]

    def events_on_camera(self, camera: str, window: int = 3600) -> list:
        cutoff = time.time() - window
        return [e for e in self.event_history if e["camera"] == camera and e["timestamp"] > cutoff]

    def recent_other_cameras(self, camera: str, window: int = 300) -> list:
        cutoff = time.time() - window
        return [e for e in self.event_history if e["camera"] != camera and e["timestamp"] > cutoff]

    def is_anomaly(self, camera: str) -> bool:
        return len(self.events_on_camera(camera, 3600)) > ANOMALY_THRESH

    # ── Narrative generation ──────────────────────────────────────────────────

    def build_narrative(self, camera: str, cv_detection: list, description: str) -> str:
        """
        Generate a smart 1-2 sentence announcement using LLM + full context.
        Falls back to simple text if LLM doesn't respond in time.
        """
        now        = datetime.now()
        hour       = now.hour
        time_label = (
            "middle of the night" if 0 <= hour < 5 else
            "early morning"       if 5 <= hour < 8 else
            "morning"             if 8 <= hour < 12 else
            "afternoon"           if 12 <= hour < 17 else
            "evening"             if 17 <= hour < 21 else
            "night"
        )

        cam_loc      = CAMERA_LOCATIONS.get(camera, camera)
        home         = self.who_is_home()
        hour_count   = len(self.events_on_camera(camera, 3600))
        anomaly      = self.is_anomaly(camera)
        other_events = self.recent_other_cameras(camera, 300)
        other_cams   = list({e["camera"] for e in other_events})

        lines = [
            f"Camera: {cam_loc}",
            f"Time: {time_label} ({now.strftime('%I:%M %p')})",
        ]
        if cv_detection:
            lines.append(f"Detected: {', '.join(cv_detection)}")
        if description:
            lines.append(f"Blink says: {description}")
        if home:
            lines.append(f"Known home: {', '.join(home)}")
        else:
            lines.append("No one known to be home")
        if hour_count > 1:
            lines.append(f"Events on this camera in the last hour: {hour_count}")
        if anomaly:
            lines.append("Unusually high activity for this camera")
        if other_cams:
            lines.append(f"Other cameras also fired in last 5 min: {', '.join(other_cams)}")

        context_block = "\n".join(lines)

        prompt = (
            f"You are Echo. You watch over Jake's house in Altoona PA. "
            f"A motion event just happened.\n\n"
            f"{context_block}\n\n"
            f"Write 1-2 sentences announcing this event. Be specific. "
            f"If it's unusual, say so. If no one is home and there's motion, say so. "
            f"If multiple cameras fired at once, mention it. "
            f"Don't say 'I detected' or 'the camera' — just describe what's happening. "
            f"Short, direct, no filler.\n\nEcho:"
        )

        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=15,
            )
            text = resp.json().get("response", "").strip()
            if text:
                # Strip accidental "Echo:" prefix
                if text.lower().startswith("echo:"):
                    text = text[5:].strip()
                print(f"[context] Narrative: {text[:100]}", flush=True)
                return text
        except Exception as e:
            print(f"[context] LLM narrative failed ({e}) — using fallback", flush=True)

        # Fallback — still smarter than before
        if description:
            return description
        if cv_detection:
            objects = ", ".join(cv_detection)
            if anomaly:
                return f"{objects} on {camera} — unusually high activity tonight."
            return f"{objects} on {camera}."
        if anomaly:
            return f"Motion on {camera} — more activity than usual."
        return f"Motion on {camera}."


# ── Singleton ─────────────────────────────────────────────────────────────────

_ctx: EchoContext = None

def get_context() -> EchoContext:
    global _ctx
    if _ctx is None:
        _ctx = EchoContext()
    return _ctx
