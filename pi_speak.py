"""
pi_speak.py
Tiny speak server — runs on the Pi.
Accepts POST /speak {"text": "..."} and speaks through Pi speakers.
Calls XTTS server on PC for voice synthesis (Blondie voice clone).

Run on Pi: python pi_speak.py
"""

import subprocess
import requests
from flask import Flask, request, jsonify

XTTS_URL     = "http://192.168.68.65:5200/tts_to_audio/"
SPEAKER_WAV  = "1"   # voice sample to use from Echos voice folder
APLAY_DEVICE = "plughw:2,0"  # USB speakers — card 2

app = Flask(__name__)
print("Pi speak server ready (XTTS voice).")


@app.route("/speak", methods=["POST"])
def speak():
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "no text"}), 400

    print(f"Speaking: {text}")
    try:
        resp = requests.post(
            XTTS_URL,
            json={"text": text, "speaker_wav": SPEAKER_WAV, "language": "en"},
            timeout=30,
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
