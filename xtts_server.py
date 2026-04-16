"""
xtts_server.py
Echo's XTTS v2 voice server — runs on PC, clones Blondie voice.
Pi calls POST /speak with {"text": "..."}, gets WAV audio back.

Run in xtts conda env:
  conda activate xtts
  python xtts_server.py
"""

import os
import io
import glob
from flask import Flask, request, send_file, jsonify
from TTS.api import TTS
import torch

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR    = r"C:\Users\jrsrl\Desktop\Echos voice"
PORT         = 5200

# Convert MP3s to WAV on first run if needed
def get_wav_samples():
    wavs = glob.glob(os.path.join(VOICE_DIR, "*.wav"))
    if not wavs:
        print("Converting MP3s to WAV...")
        from pydub import AudioSegment
        for mp3 in glob.glob(os.path.join(VOICE_DIR, "*.mp3")):
            wav_path = mp3.replace(".mp3", ".wav")
            AudioSegment.from_mp3(mp3).export(wav_path, format="wav")
            wavs.append(wav_path)
        print(f"Converted {len(wavs)} files.")
    return wavs

app = Flask(__name__)

print("Loading XTTS model (first run downloads ~2GB)...")
device = "cuda" if torch.cuda.is_available() else "cpu"
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
print(f"XTTS ready on {device}.")

SPEAKER_WAVS = get_wav_samples()
print(f"Voice reference: {len(SPEAKER_WAVS)} samples loaded.")


@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "no text"}), 400

    buf = io.BytesIO()
    tts.tts_to_file(
        text=text,
        speaker_wav=SPEAKER_WAVS,
        language="en",
        file_path=buf,
    )
    buf.seek(0)
    return send_file(buf, mimetype="audio/wav")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "device": device, "samples": len(SPEAKER_WAVS)})


if __name__ == "__main__":
    print(f"XTTS server running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
