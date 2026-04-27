"""
echo_server.py
Echo Command Center backend.
Manages processes, streams logs, relays chat, fetches Moltbook stats.

Install: pip install flask flask-socketio flask-cors
Run:     python echo_server.py
Then open echo_gui.html in Chrome.
"""

import os
import re
import json
import time
import subprocess
import threading
import requests
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE        = os.path.join(BASE_DIR, "moltbook_creds.json")
AWARENESS_FILE    = os.path.join(BASE_DIR, "awareness_config.json")
IDENTITY_FILE     = os.path.join(BASE_DIR, "identity.md")
HEARTBEAT_FILE    = os.path.join(BASE_DIR, "latest_heartbeat.json")
ECHO_MEMORY_FILE  = os.path.join(BASE_DIR, "Echo_Memory.txt")
BLINK_EVENTS_DIR  = os.path.join(BASE_DIR, "cache", "blink", "events")
BLINK_THUMBS_DIR  = os.path.join(BASE_DIR, "cache", "blink", "thumbs")
OLLAMA_URL        = "http://localhost:11434/api/generate"
OLLAMA_MODEL      = "echo"
MOLTBOOK_URL      = "https://www.moltbook.com/api/v1"

app = Flask(__name__)
app.config["SECRET_KEY"] = "echo-command-center"
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET","POST","OPTIONS"], "allow_headers": ["Content-Type"]}})
sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Process registry ───────────────────────────────────────────────────────

JOBS = {
    "moltbook": {
        "label": "Moltbook",
        "cmd":   ["python", os.path.join(BASE_DIR, "moltbook_session.py")],
        "proc":  None,
        "status": "stopped",
    },
    "discord": {
        "label": "Discord",
        "cmd":   ["python", os.path.join(BASE_DIR, "discord_echo.py")],
        "proc":  None,
        "status": "stopped",
    },
    "blink": {
        "label": "Blink Cameras",
        "cmd":   ["python", os.path.join(BASE_DIR, "blink_watcher.py")],
        "proc":  None,
        "status": "stopped",
    },
    # Voice (echo_voice.py) runs on the Pi — not managed here
}


def _stream_output(job_id: str, proc):
    try:
        for line in iter(proc.stdout.readline, b""):
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                sio.emit("job_log", {"job": job_id, "line": text, "ts": datetime.now().strftime("%H:%M:%S")})
        JOBS[job_id]["status"] = "stopped"
        sio.emit("job_status", {"job": job_id, "status": "stopped"})
    except Exception:
        pass


def start_job(job_id: str):
    job = JOBS.get(job_id)
    if not job or job["status"] == "running":
        return
    proc = subprocess.Popen(
        job["cmd"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    job["proc"]   = proc
    job["status"] = "running"
    sio.emit("job_status", {"job": job_id, "status": "running"})
    t = threading.Thread(target=_stream_output, args=(job_id, proc), daemon=True)
    t.start()


def stop_job(job_id: str):
    job = JOBS.get(job_id)
    if not job or not job["proc"]:
        return
    job["proc"].terminate()
    job["proc"]   = None
    job["status"] = "stopped"
    sio.emit("job_status", {"job": job_id, "status": "stopped"})


# ── GUI route ──────────────────────────────────────────────────────────────

@app.route("/")
def serve_gui():
    return send_from_directory(BASE_DIR, "echo_gui.html")


# ── Job routes ─────────────────────────────────────────────────────────────

@app.route("/api/jobs")
def get_jobs():
    return jsonify({k: {"label": v["label"], "status": v["status"]} for k, v in JOBS.items()})


@app.route("/api/jobs/<job_id>/start", methods=["POST"])
def api_start_job(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    start_job(job_id)
    return jsonify({"status": "started"})


@app.route("/api/jobs/<job_id>/stop", methods=["POST"])
def api_stop_job(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    stop_job(job_id)
    return jsonify({"status": "stopped"})


@app.route("/api/jobs/<job_id>/restart", methods=["POST"])
def api_restart_job(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    stop_job(job_id)
    time.sleep(0.5)
    start_job(job_id)
    return jsonify({"status": "restarted"})


@app.route("/api/start_all", methods=["POST"])
def api_start_all():
    for job_id in JOBS:
        start_job(job_id)
    return jsonify({"status": "ok"})


@app.route("/api/stop_all", methods=["POST"])
def api_stop_all():
    for job_id in JOBS:
        stop_job(job_id)
    return jsonify({"status": "ok"})


# ── Chat route ─────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data       = request.json or {}
    user_input = data.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "empty message"}), 400

    try:
        with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
            identity = f.read().strip()
    except Exception:
        identity = "You are Echo."

    prompt = f"Jake: {user_input}\nEcho:"
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model":  OLLAMA_MODEL,
            "prompt": f"<<SYS>>\n{identity}\n<</SYS>>\n\n{prompt}",
            "stream": False,
        }, timeout=120)
        reply = resp.json().get("response", "").strip()
        # Strip any conversation replay
        lines  = reply.split("\n")
        output = []
        for line in lines:
            import re
            if re.match(r"^\w[\w\s]*:", line) and output:
                break
            output.append(line)
        reply = "\n".join(output).strip()
        # Strip any leaked emotional state tags
        import re
        reply = re.sub(r"<[^>]+>", "", reply).strip()
    except Exception as e:
        reply = f"(Echo couldn't respond — {e})"

    # Speak reply through Pi speakers
    try:
        requests.post("http://192.168.68.84:5100/speak", json={"text": reply}, timeout=5)
    except Exception:
        pass

    return jsonify({"reply": reply})


# ── Awareness config routes ────────────────────────────────────────────────

@app.route("/api/awareness/config", methods=["GET"])
def get_awareness_config():
    try:
        with open(AWARENESS_FILE) as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({})

@app.route("/api/awareness/config", methods=["POST"])
def save_awareness_config():
    data = request.get_json(force=True, silent=True) or {}
    with open(AWARENESS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return jsonify({"status": "saved"})

@app.route("/api/awareness/save")
def save_awareness_config_get():
    data_str = request.args.get("data", "{}")
    try:
        data = json.loads(data_str)
    except Exception:
        data = {}
    with open(AWARENESS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[awareness] Config saved: {data}")
    return jsonify({"status": "saved"})


# ── Identify route ─────────────────────────────────────────────────────────

@app.route("/api/identify", methods=["POST"])
def api_identify():
    try:
        from echo_identify import identify_person
        people = identify_person(timeout=30)
    except Exception as e:
        people = ["error"]
        print(f"[identify] {e}")
    return jsonify({"people": people})


# ── Moltbook routes ────────────────────────────────────────────────────────

@app.route("/api/moltbook/stats")
def api_moltbook_stats():
    try:
        with open(CREDS_FILE) as f:
            creds = json.load(f)
        headers = {"Authorization": f"Bearer {creds['api_key']}"}

        # /home gives karma + notifications; /agents/me gives follower_count
        home_resp    = requests.get(f"{MOLTBOOK_URL}/home",       headers=headers, timeout=10)
        profile_resp = requests.get(f"{MOLTBOOK_URL}/agents/me",  headers=headers, timeout=10)

        home    = home_resp.json()    if home_resp.ok    else {}
        profile = profile_resp.json() if profile_resp.ok else {}

        account  = home.get("your_account", {})
        activity = home.get("activity_on_your_posts", [])
        agent    = profile.get("agent", profile)

        return jsonify({
            "karma":         account.get("karma", agent.get("karma", "—")),
            "followers":     agent.get("follower_count", agent.get("followers", "—")),
            "following":     agent.get("following_count", "—"),
            "posts":         agent.get("posts_count", "—"),
            "username":      account.get("name", agent.get("name", "echo_7337")),
            "notifications": account.get("unread_notification_count", 0),
            "activity":      activity[:5],
        })
    except Exception as e:
        return jsonify({"error": str(e), "karma": "—", "followers": "—", "notifications": 0}), 200


@app.route("/api/moltbook/session", methods=["POST"])
def api_moltbook_session():
    """Trigger an immediate Moltbook session in a thread."""
    def _run():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "moltbook_session",
            os.path.join(BASE_DIR, "moltbook_session.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run_session()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"status": "session started"})


# ── Memory backup route ───────────────────────────────────────────────────

@app.route("/api/memory/backup", methods=["POST"])
def api_memory_backup():
    """Git add → commit → push the memories folder."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "-C", BASE_DIR, "add", "-A", "memories/"],
            capture_output=True, timeout=30
        )
        commit = subprocess.run(
            ["git", "-C", BASE_DIR, "commit", "-m", f"memory backup {ts}"],
            capture_output=True, text=True, timeout=30
        )
        if "nothing to commit" in commit.stdout or "nothing to commit" in commit.stderr:
            return jsonify({"status": "nothing new to back up"})
        push = subprocess.run(
            ["git", "-C", BASE_DIR, "push"],
            capture_output=True, text=True, timeout=60
        )
        if push.returncode == 0:
            return jsonify({"status": "backed up ✓"})
        else:
            return jsonify({"status": f"push failed — {push.stderr.strip()}"}), 500
    except Exception as e:
        return jsonify({"status": f"error — {e}"}), 500


# ── Webcam intelligence routes ────────────────────────────────────────────

_latest_webcam_event = {}

@app.route("/api/webcam/event", methods=["POST"])
def api_webcam_event():
    global _latest_webcam_event
    event = request.get_json(silent=True) or {}
    _latest_webcam_event = event
    # Emit to GUI via Socket.IO so dashboard can react in real time
    sio.emit("webcam_event", event)
    # Greet known people via voice if newly seen
    known = event.get("presence", {}).get("known_ids", [])
    for person in known:
        sio.emit("job_log", {"job": "blink", "line": f"[webcam] {person} at desk", "ts": datetime.now().strftime("%H:%M:%S")})
    return jsonify({"status": "ok"})

@app.route("/api/webcam/latest")
def api_webcam_latest():
    return jsonify(_latest_webcam_event)


# ── Echo state route ───────────────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    return jsonify({"emotion": "warm", "baseline": "warm"})


# ── Awareness dashboard routes ─────────────────────────────────────────────

@app.route("/awareness")
def serve_awareness():
    return send_from_directory(BASE_DIR, "awareness.html")

@app.route("/blink/clip/<path:filename>")
def serve_blink_clip(filename):
    clip_dir = os.path.join(BASE_DIR, "cache", "blink", "clips")
    return send_from_directory(clip_dir, filename)

@app.route("/api/awareness/events")
def api_awareness_events():
    events = []
    try:
        files = sorted(
            [f for f in os.listdir(BLINK_EVENTS_DIR) if f.endswith(".json") and f != "latest_event.json"],
            reverse=True
        )
        for fname in files[:60]:
            try:
                with open(os.path.join(BLINK_EVENTS_DIR, fname), encoding="utf-8") as f:
                    ev = json.load(f)
                if ev.get("thumbnail"):
                    ev["thumb_file"] = os.path.basename(ev["thumbnail"])
                if ev.get("clip"):
                    ev["clip_file"] = os.path.basename(ev["clip"])
                events.append(ev)
            except Exception:
                pass
    except Exception as e:
        print(f"[awareness] events error: {e}")
    return jsonify({"events": events})

@app.route("/api/awareness/health")
def api_awareness_health():
    try:
        health_file = os.path.join(BASE_DIR, "cache", "blink", "camera_health.json")
        with open(health_file, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({})

@app.route("/api/awareness/household")
def api_awareness_household():
    try:
        ctx_file = os.path.join(BASE_DIR, "cache", "blink", "echo_context.json")
        with open(ctx_file, encoding="utf-8") as f:
            data = json.load(f)
        household    = data.get("household", {})
        now          = time.time()
        presence_ttl = 4 * 3600
        people = []
        for person, ts in sorted(household.items(), key=lambda x: x[1], reverse=True):
            age = now - ts
            if age < presence_ttl:
                people.append({
                    "name":       person,
                    "last_seen":  datetime.fromtimestamp(ts).strftime("%I:%M %p"),
                    "minutes_ago": int(age / 60),
                })
        return jsonify({"home": people})
    except Exception:
        return jsonify({"home": []})

@app.route("/api/awareness/summary")
def api_awareness_summary():
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        events = []
        for fname in sorted(os.listdir(BLINK_EVENTS_DIR)):
            if not fname.endswith(".json") or fname == "latest_event.json":
                continue
            try:
                with open(os.path.join(BLINK_EVENTS_DIR, fname), encoding="utf-8") as f:
                    ev = json.load(f)
                if ev.get("timestamp", 0) > today_start:
                    events.append(ev)
            except Exception:
                pass

        if not events:
            return jsonify({"summary": "No camera events today.", "event_count": 0, "cameras": []})

        by_camera = {}
        for ev in events:
            cam = ev.get("camera", "unknown")
            by_camera.setdefault(cam, []).append(ev)

        digest_lines = []
        for cam, cam_events in sorted(by_camera.items()):
            times = [datetime.fromtimestamp(e["timestamp"]).strftime("%I:%M %p") for e in cam_events]
            sample = ", ".join(times[:6]) + ("..." if len(times) > 6 else "")
            digest_lines.append(f"{cam}: {len(cam_events)} events — {sample}")
        digest = "\n".join(digest_lines)

        prompt = (
            f"You are Echo. Here is today's camera event log for Jake's house:\n\n{digest}\n\n"
            f"Write a 3-5 sentence summary of the day's activity around the house. "
            f"Mention patterns, anything unusual, quiet stretches. "
            f"Speak like you were actually watching all day. Direct, no filler.\n\nEcho:"
        )
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=30)
        summary = resp.json().get("response", "").strip()
        if summary.lower().startswith("echo:"):
            summary = summary[5:].strip()

        return jsonify({"summary": summary, "event_count": len(events), "cameras": list(by_camera.keys())})
    except Exception as e:
        return jsonify({"summary": f"Summary unavailable — {e}", "event_count": 0, "cameras": []})


# ── Live feed routes ───────────────────────────────────────────────────────

@app.route("/api/latest/heartbeat")
def api_latest_heartbeat():
    try:
        with open(HEARTBEAT_FILE, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({"text": None, "timestamp": None})


@app.route("/api/latest/scribe")
def api_latest_scribe():
    entries = []
    try:
        with open(ECHO_MEMORY_FILE, encoding="utf-8") as f:
            lines = [l.rstrip() for l in f if l.strip()]
        for line in lines[-20:]:
            m = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s+\(([^)]+)\)\s+(.*)', line)
            if m:
                entries.append({"ts": m.group(1), "category": m.group(2), "fact": m.group(3)})
            else:
                entries.append({"ts": "", "category": "", "fact": line})
    except Exception:
        pass
    return jsonify({"entries": entries})


@app.route("/api/latest/blink")
def api_latest_blink():
    try:
        event_file = os.path.join(BLINK_EVENTS_DIR, "latest_event.json")
        with open(event_file, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({"camera": None, "datetime": None, "thumb": None})


@app.route("/blink/thumb/<path:filename>")
def serve_blink_thumb(filename):
    return send_from_directory(BLINK_THUMBS_DIR, filename)


# ── SocketIO ───────────────────────────────────────────────────────────────

@sio.on("connect")
def on_connect():
    for job_id, job in JOBS.items():
        sio.emit("job_status", {"job": job_id, "status": job["status"]})


if __name__ == "__main__":
    print("=" * 50)
    print("  Echo Command Center")
    print("  http://localhost:5050")
    print("  Open echo_gui.html in Chrome")
    print("=" * 50)
    sio.run(app, host="0.0.0.0", port=5050, debug=False)
