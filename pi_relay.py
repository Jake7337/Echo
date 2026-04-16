"""
pi_relay.py
Pi-side log relay and process manager.
Runs on the Pi alongside pi_speak.py and echo_voice.py.
Streams logs to the GUI via SocketIO.

Run on Pi: python pi_relay.py
Install:   pip install flask flask-socketio --break-system-packages
"""

import os
import subprocess
import threading
from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "echo-pi-relay"
CORS(app)
sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

JOBS = {
    "pi_speak": {
        "label": "Pi Speak",
        "cmd":   ["python", os.path.join(BASE_DIR, "pi_speak.py")],
        "proc":  None,
        "status": "stopped",
    },
    "echo_voice": {
        "label": "Echo Voice",
        "cmd":   ["python", os.path.join(BASE_DIR, "echo_voice.py")],
        "proc":  None,
        "status": "stopped",
    },
}


AUTORESTART_JOBS = {"pi_speak"}  # jobs that should restart automatically if they crash

def _stream_output(job_id: str, proc):
    import time
    try:
        for line in iter(proc.stdout.readline, b""):
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                from datetime import datetime
                ts = datetime.now().strftime("%H:%M:%S")
                sio.emit("pi_log", {"job": job_id, "line": text, "ts": ts})
        JOBS[job_id]["status"] = "stopped"
        sio.emit("pi_status", {"job": job_id, "status": "stopped"})
        if job_id in AUTORESTART_JOBS and JOBS[job_id].get("proc") is not None:
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            sio.emit("pi_log", {"job": job_id, "line": f"[relay] {job_id} exited — restarting in 3s...", "ts": ts})
            time.sleep(3)
            start_job(job_id)
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
    )
    job["proc"]   = proc
    job["status"] = "running"
    sio.emit("pi_status", {"job": job_id, "status": "running"})
    t = threading.Thread(target=_stream_output, args=(job_id, proc), daemon=True)
    t.start()


def stop_job(job_id: str):
    job = JOBS.get(job_id)
    if not job or not job["proc"]:
        return
    job["proc"].terminate()
    job["proc"]   = None
    job["status"] = "stopped"
    sio.emit("pi_status", {"job": job_id, "status": "stopped"})


@app.route("/api/jobs")
def get_jobs():
    return jsonify({k: {"label": v["label"], "status": v["status"]} for k, v in JOBS.items()})


@app.route("/api/jobs/<job_id>/start", methods=["POST"])
def api_start(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    start_job(job_id)
    return jsonify({"status": "started"})


@app.route("/api/jobs/<job_id>/stop", methods=["POST"])
def api_stop(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    stop_job(job_id)
    return jsonify({"status": "stopped"})


@app.route("/api/jobs/<job_id>/restart", methods=["POST"])
def api_restart(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    stop_job(job_id)
    import time; time.sleep(0.5)
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


@app.route("/ping")
def ping():
    return jsonify({"status": "alive"})


@sio.on("connect")
def on_connect():
    for job_id, job in JOBS.items():
        sio.emit("pi_status", {"job": job_id, "status": job["status"]})


if __name__ == "__main__":
    print("Pi relay starting — auto-launching jobs...")
    start_job("pi_speak")
    start_job("echo_voice")
    print("Pi relay running on port 5101")
    sio.run(app, host="0.0.0.0", port=5101, debug=False, allow_unsafe_werkzeug=True)
