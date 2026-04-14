"""
pi_speak.py
Tiny speak server — runs on the Pi.
Accepts POST /speak {"text": "..."} and speaks through Pi speakers.

Run on Pi: python pi_speak.py
Install:   pip install flask piper-tts
"""

import io
import os
import wave
import subprocess
from flask import Flask, request, jsonify
from piper import PiperVoice

PIPER_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "en_US-lessac-medium.onnx")
APLAY_DEVICE = "plughw:2,0"  # USB speakers — card 2

app = Flask(__name__)
print("Loading voice...")
voice = PiperVoice.load(PIPER_MODEL)
print("Pi speak server ready.")


@app.route("/speak", methods=["POST"])
def speak():
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "no text"}), 400

    print(f"Speaking: {text}")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        voice.synthesize_wav(text, wav)
    buf.seek(0)

    proc = subprocess.Popen(
        ["aplay", "-D", APLAY_DEVICE, "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.communicate(input=buf.read())
    return jsonify({"status": "ok"})


@app.route("/ping")
def ping():
    return jsonify({"status": "alive"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, debug=False)
