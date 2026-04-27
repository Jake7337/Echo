"""
webcam_intel/main.py
Echo Webcam Intelligence Module — browser-based viewer.

Run from Echo2 folder:
    python -m webcam_intel.main

Then open: http://localhost:5051

Stream with overlays at: http://localhost:5051/stream
Latest event JSON at:    http://localhost:5051/event
"""

import sys
import os
import time
import json
import logging
import cv2
import threading
import numpy as np
from flask import Flask, Response, jsonify, render_template_string

# ── Logging setup (before any module imports) ─────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,           # INFO/DEBUG is noisy; bump up when debugging
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("webcam_intel.main")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webcam_intel.camera   import Camera
from webcam_intel.pipeline import Pipeline
from webcam_intel import events as ev_bus

# ── Config ────────────────────────────────────────────────────────────────────
CAM_INDEX      = 0
CAM_WIDTH      = 1280
CAM_HEIGHT     = 720
CAM_FPS        = 15
PUBLISH_EVENTS = True
EVENT_INTERVAL = 1.0
PORT           = 5051

# Colors (BGR for OpenCV drawing)
CYAN  = (220, 210,   0)
GREEN = ( 80, 220,  80)
WHITE = (210, 210, 210)
DIM   = ( 90,  90, 110)
RED   = ( 60,  60, 200)
AMBER = (  0, 170, 255)
FONT  = cv2.FONT_HERSHEY_SIMPLEX

# ── Global state ──────────────────────────────────────────────────────────────
_latest_frame = None
_latest_event = {}
_frame_lock   = threading.Lock()
_debug        = True

# ── Drawing ───────────────────────────────────────────────────────────────────

def draw_debug(frame, event: dict):
    fh, fw = frame.shape[:2]

    for face in event.get("faces", []):
        x, y, w, h = face["bbox"]
        name  = face["id"]
        conf  = face["confidence"]
        emo   = face.get("emotion", {})
        color = CYAN if name != "unknown" else DIM

        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        label = f"{name}  {conf:.0%}" if conf > 0 else name
        cv2.rectangle(frame, (x, y-22), (x + len(label)*9, y), color, -1)
        cv2.putText(frame, label, (x+4, y-6), FONT, 0.5, (0,0,0), 1, cv2.LINE_AA)

        emo_lbl  = emo.get("label", "")
        emo_conf = emo.get("confidence", 0.0)
        if emo_lbl and emo_lbl not in ("neutral", "unknown", ""):
            cv2.putText(frame, f"{emo_lbl}  {emo_conf:.0%}",
                        (x, y+h+18), FONT, 0.48, AMBER, 1, cv2.LINE_AA)

    for g in event.get("gestures", []):
        x, y, w, h = g["bbox"]
        gtype = g["type"].replace("_", " ").upper()
        cv2.rectangle(frame, (x, y), (x+w, y+h), GREEN, 2)
        cv2.putText(frame, f"{gtype} {g['confidence']:.0%}",
                    (x, y-8), FONT, 0.52, GREEN, 1, cv2.LINE_AA)

    presence = event.get("presence", {})
    known    = presence.get("known_ids", [])
    n_faces  = presence.get("num_faces", 0)
    hud = [f"Faces: {n_faces}", f"Known: {', '.join(known) if known else 'none'}"]
    for i, line in enumerate(hud):
        cv2.putText(frame, line, (10, 22 + i*18), FONT, 0.48, DIM, 1, cv2.LINE_AA)

    cv2.putText(frame, "ECHO  WEBCAM  INTEL",
                (fw - 230, 22), FONT, 0.5, CYAN, 1, cv2.LINE_AA)


# ── Capture loop (background thread) ─────────────────────────────────────────

def capture_loop(cam: Camera, pipeline: Pipeline):
    global _latest_frame, _latest_event
    meta          = cam.get_meta()
    last_published = 0.0

    while True:
        try:
            frame = cam.read()
            if frame is None:
                time.sleep(0.05)
                continue

            event, annotated = pipeline.process(frame)
            event["raw_metadata"] = meta

            display = annotated.copy()
            if _debug:
                draw_debug(display, event)

            # Encode to JPEG for streaming
            ret, buf = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                with _frame_lock:
                    _latest_frame = buf.tobytes()
                    _latest_event = event

            # Publish to echo_server
            now = time.time()
            if PUBLISH_EVENTS and (now - last_published) >= EVENT_INTERVAL:
                if event["presence"]["any_person"] or event["gestures"]:
                    ev_bus.publish(event)
                    last_published = now

        except Exception as e:
            import traceback
            print(f"[capture_loop] Error: {e}", flush=True)
            traceback.print_exc()
            time.sleep(0.1)  # brief pause then keep running


# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Echo Webcam Intel</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0a0a0f;
  font-family: 'Courier New', monospace;
  color: #c8c8d8;
  display: grid;
  grid-template-rows: 40px 1fr;
  height: 100vh;
}
#header {
  display: flex; align-items: center; gap: 20px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(0,245,255,0.15);
  background: rgba(0,0,0,0.5);
}
#header h1 { font-size: 0.6rem; letter-spacing: 4px; text-transform: uppercase; color: #00f5ff; }
.hbtn {
  font-family: 'Courier New', monospace;
  font-size: 0.5rem; letter-spacing: 1px; text-transform: uppercase;
  background: transparent; border: 1px solid rgba(0,245,255,0.3);
  color: rgba(0,245,255,0.6); padding: 4px 10px; border-radius: 4px;
  cursor: pointer; transition: all 0.2s; margin-left: auto;
}
.hbtn:hover { border-color: #00f5ff; color: #00f5ff; }
#main {
  display: grid; grid-template-columns: 1fr 280px;
  gap: 10px; padding: 10px; overflow: hidden;
}
#stream-wrap {
  background: #000; border-radius: 10px; overflow: hidden;
  border: 1px solid rgba(0,245,255,0.2);
  display: flex; align-items: center; justify-content: center;
}
#stream { width: 100%; height: 100%; object-fit: contain; display: block; }
#sidebar { display: flex; flex-direction: column; gap: 10px; overflow: hidden; }
.panel {
  background: rgba(10,10,25,0.75);
  border-radius: 10px; padding: 12px;
  border: 1px solid rgba(255,255,255,0.07);
}
.panel-title {
  font-size: 0.5rem; letter-spacing: 3px; text-transform: uppercase;
  color: #555570; margin-bottom: 10px;
}
.stat { font-size: 0.7rem; color: #00f5ff; margin-bottom: 4px; }
.stat span { color: #c8c8d8; }
#event-json {
  font-size: 0.5rem; color: #7a7a9a; line-height: 1.5;
  overflow-y: auto; flex: 1;
  white-space: pre-wrap; word-break: break-all;
  scrollbar-width: thin; scrollbar-color: #555570 transparent;
}
</style>
</head>
<body>
<div id="header">
  <h1>Echo — Webcam Intelligence</h1>
  <button class="hbtn" onclick="toggleDebug()">Toggle Overlay</button>
  <a href="http://localhost:5050" style="font-size:0.5rem;color:#555570;text-decoration:none;
     border:1px solid #555570;padding:4px 10px;border-radius:4px;margin-left:8px;">
    ← Command Center
  </a>
</div>
<div id="main">
  <div id="stream-wrap">
    <img id="stream" src="/frame" alt="webcam">
  </div>
  <div id="sidebar">
    <div class="panel">
      <div class="panel-title">Presence</div>
      <div class="stat">Faces: <span id="n-faces">0</span></div>
      <div class="stat">Known: <span id="known">—</span></div>
      <div class="stat">Gestures: <span id="gestures">—</span></div>
    </div>
    <div class="panel" style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
      <div class="panel-title">Live Event</div>
      <div id="event-json">waiting...</div>
    </div>
  </div>
</div>
<script>
// Poll event data every 500ms
async function pollEvent() {
  try {
    const r = await fetch('/event');
    const e = await r.json();
    const p = e.presence || {};
    document.getElementById('n-faces').textContent  = p.num_faces ?? 0;
    document.getElementById('known').textContent    = (p.known_ids||[]).join(', ') || 'none';
    const gs = (e.gestures||[]).map(g=>g.type.replace(/_/g,' ')).join(', ');
    document.getElementById('gestures').textContent = gs || 'none';
    document.getElementById('event-json').textContent = JSON.stringify(e, null, 2);
  } catch(err) {}
}

// Refresh camera frame as fast as it loads (no fixed interval)
const img = document.getElementById('stream');
function loadNextFrame() {
  const next = new Image();
  next.onload = () => {
    img.src = next.src;
    setTimeout(loadNextFrame, 50); // ~20fps cap
  };
  next.onerror = () => setTimeout(loadNextFrame, 200);
  next.src = '/frame?t=' + Date.now();
}

async function toggleDebug() {
  await fetch('/toggle_debug', {method:'POST'});
}

setInterval(pollEvent, 500);
pollEvent();
loadNextFrame();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return PAGE

@app.route("/frame")
def frame_jpg():
    """Single JPEG frame — browser polls this repeatedly instead of MJPEG stream."""
    with _frame_lock:
        f = _latest_frame
    if f is None:
        return Response(status=204)
    return Response(f, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store"})

@app.route("/event")
def event():
    return jsonify(_latest_event)

@app.route("/toggle_debug", methods=["POST"])
def toggle_debug():
    global _debug
    _debug = not _debug
    return jsonify({"debug": _debug})


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cam      = Camera(CAM_INDEX, CAM_WIDTH, CAM_HEIGHT, CAM_FPS)
    pipeline = Pipeline(face_interval=5)

    cam.start()
    time.sleep(0.5)

    t = threading.Thread(target=capture_loop, args=(cam, pipeline), daemon=True)
    t.start()

    print(f"\n  Open in Chrome: http://localhost:{PORT}", flush=True)
    print(f"  Latest frame:   http://localhost:{PORT}/frame", flush=True)
    print(f"  Event JSON:     http://localhost:{PORT}/event", flush=True)
    print(f"  Face encodings loading in background — will print when ready.", flush=True)
    print(f"  Ctrl+C to quit\n", flush=True)

    try:
        from waitress import serve
        print(f"  Using waitress WSGI server.", flush=True)
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        print(f"  waitress not found, using Flask dev server.", flush=True)
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True, use_reloader=False)
    except Exception as e:
        import traceback
        print(f"\n[server] Crashed: {e}", flush=True)
        traceback.print_exc()
    finally:
        cam.stop()
        pipeline.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped.", flush=True)
    except Exception as e:
        log.exception("Fatal error in webcam_intel: %s", e)
        sys.exit(1)
