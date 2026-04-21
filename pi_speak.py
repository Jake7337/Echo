"""
pi_speak.py
Tiny speak server — runs on the Pi.
Accepts POST /speak {"text": "..."} and speaks through Pi speakers.
Calls XTTS server on PC for voice synthesis (Blondie voice clone).

Run on Pi: python pi_speak.py
"""

import subprocess
import requests
import random
from flask import Flask, request, jsonify

XTTS_URL     = "http://192.168.68.80:5200/tts_to_audio/"
APLAY_DEVICE = "plughw:2,0"  # USB speakers — card 2

SPEAKER_WAVS = [f"echo_{i:03d}" for i in range(1, 83)]

app = Flask(__name__)
print("Pi speak server ready (XTTS voice).")


@app.route("/speak", methods=["POST"])
def speak():
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "no text"}), 400

    # Truncate long responses — XTTS times out on walls of text
    if len(text) > 400:
        text = text[:400].rsplit(" ", 1)[0] + "..."
    speaker = random.choice(SPEAKER_WAVS)
    print(f"Speaking: {text}")
    try:
        resp = requests.post(
            XTTS_URL,
            json={"text": text, "speaker_wav": speaker, "language": "en"},
            timeout=60,
        )
        resp.raise_for_status()
        wav_bytes = resp.content
    except Exception as e:
        print(f"[pi_speak] XTTS error — {e}")
        return jsonify({"error": str(e)}), 500

    proc = subprocess.Popen(
        ["aplay", "-D", APLAY_DEVICE, "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.communicate(input=wav_bytes)
    return jsonify({"status": "ok"})


@app.route("/ping")
def ping():
    return jsonify({"status": "alive"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, debug=False)
