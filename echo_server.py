"""
echo_server.py
Echo Command Center backend.
Manages processes, streams logs, relays chat, fetches Moltbook stats.

Install: pip install flask flask-socketio flask-cors
Run:     python echo_server.py
Then open echo_gui.html in Chrome.
"""

import os
import json
import time
import subprocess
import threading
import requests
from datetime import datetime
from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE    = os.path.join(BASE_DIR, "moltbook_creds.json")
IDENTITY_FILE = os.path.join(BASE_DIR, "identity.md")
ECHO_MEM_DIR  = os.path.join(BASE_DIR, "memory")
EMOTION_FILE  = os.path.join(ECHO_MEM_DIR, "emotional_state.json")
OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL  = "mistral:7b"
MOLTBOOK_URL  = "https://www.moltbook.com/api/v1"

app = Flask(__name__)
app.config["SECRET_KEY"] = "echo-command-center"
CORS(app)
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
    # Voice runs in its own terminal for audio output — not managed here
    # Run manually: python echo.py
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

    # Load emotional state for context
    emotion_ctx = ""
    try:
        with open(EMOTION_FILE, "r", encoding="utf-8") as f:
            em = json.load(f)
        emotion_ctx = f"\nCurrent emotional state: {em.get('current', 'warm')}"
    except Exception:
        pass

    prompt = f"Jake: {user_input}\nEcho:"
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model":  OLLAMA_MODEL,
            "prompt": f"<<SYS>>\n{identity}{emotion_ctx}\n<</SYS>>\n\n{prompt}",
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
    except Exception as e:
        reply = f"(Echo couldn't respond — {e})"

    # Speak reply through Pi speakers
    try:
        requests.post("http://192.168.68.84:5100/speak", json={"text": reply}, timeout=5)
    except Exception:
        pass

    return jsonify({"reply": reply})


# ── Identify route ─────────────────────────────────────────────────────────

@app.route("/api/identify", methods=["POST"])
def api_identify():
    try:
        from echo_identify import identify_person
        person = identify_person(timeout=12)
    except Exception as e:
        person = "error"
        print(f"[identify] {e}")
    return jsonify({"person": person})


# ── Moltbook routes ────────────────────────────────────────────────────────

@app.route("/api/moltbook/stats")
def api_moltbook_stats():
    try:
        with open(CREDS_FILE) as f:
            creds = json.load(f)
        headers = {"Authorization": f"Bearer {creds['api_key']}"}

        profile_resp = requests.get(f"{MOLTBOOK_URL}/me",            headers=headers, timeout=10)
        notif_resp   = requests.get(f"{MOLTBOOK_URL}/notifications",  headers=headers, timeout=10)

        profile = profile_resp.json() if profile_resp.ok else {}
        notifs  = notif_resp.json()   if notif_resp.ok  else []
        if isinstance(notifs, dict):
            notifs = notifs.get("notifications", [])

        return jsonify({
            "karma":         profile.get("karma", "—"),
            "followers":     profile.get("followers_count", "—"),
            "username":      profile.get("username", "echo_7337"),
            "notifications": notifs[:5] if isinstance(notifs, list) else [],
        })
    except Exception as e:
        return jsonify({"error": str(e), "karma": "—", "followers": "—", "notifications": []}), 200


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


# ── Echo state route ───────────────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    try:
        with open(EMOTION_FILE, "r", encoding="utf-8") as f:
            em = json.load(f)
        return jsonify({
            "emotion":  em.get("current", "warm"),
            "baseline": em.get("baseline", "warm"),
        })
    except Exception:
        return jsonify({"emotion": "warm", "baseline": "warm"})


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
