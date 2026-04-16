"""
echo_voice.py
Echo — voice-enabled companion AI on Raspberry Pi.
Listens via Fifine mic, speaks via USB speakers, talks to Ollama on home PC.
"""

import io
import json
import os
import sys
import wave
import socket
import subprocess
import threading
import requests
import numpy as np
import speech_recognition as sr
from piper import PiperVoice
from datetime import datetime


# ── Config ─────────────────────────────────────────────────────────────────────

from voice_identify import identify_voice

OLLAMA_URL    = "http://192.168.68.65:11434/api/generate"
OLLAMA_MODEL  = "mistral:7b"
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "identity.md")
MEMORY_FILE   = os.path.join(os.path.dirname(__file__), "memory.json")
PROJECT_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "Echo_Memory.txt")
LIVED_MEMORY_FILE   = os.path.join(os.path.dirname(__file__), "echo_memories.txt")
MAX_HISTORY         = 20
MAX_LIVED_ENTRIES   = 100

MIC_CARD      = 1   # USB mic — PyAudio index 1 (ALSA hw:2,0)
SPEAKER_CARD  = 2   # USB AUDIO
PIPER_MODEL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "en_US-lessac-medium.onnx")
FACE_HOST      = "192.168.68.65"   # PC IP
FACE_PORT      = 5005
IDENTIFY_URL   = "http://192.168.68.65:5050/api/identify"

WAKE_WORD = "hey_jarvis"

_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ── Wake word ──────────────────────────────────────────────────────────────────

_oww_model = None

def _get_oww_model():
    global _oww_model
    if _oww_model is None:
        import openwakeword as _oww_pkg
        models_dir = os.path.join(os.path.dirname(_oww_pkg.__file__), "resources", "models")
        model_path = os.path.join(models_dir, "hey_jarvis_v0.1.onnx")
        print(f"[wake] Loading model: {model_path}", flush=True)
        from openwakeword.model import Model as OWWModel
        _oww_model = OWWModel(wakeword_model_paths=[model_path])
    return _oww_model

def wait_for_wake_word():
    """Block until 'Hey Jarvis' is detected. Uses arecord to avoid pyaudio/ALSA segfaults."""
    from scipy.signal import resample_poly
    model        = _get_oww_model()
    MIC_RATE     = 44100
    OWW_RATE     = 16000
    CHUNK_FRAMES = int(MIC_RATE * 80 / 1000)  # 80ms at 44100Hz = 3528 frames
    CHUNK_BYTES  = CHUNK_FRAMES * 2            # 16-bit = 2 bytes per frame

    for key in model.prediction_buffer:
        model.prediction_buffer[key].clear()

    proc = subprocess.Popen(
        ["arecord", "-D", "hw:2,0", "-f", "S16_LE", "-r", str(MIC_RATE), "-c", "1", "-q", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    print("Waiting for wake word ('Hey Jarvis')...", flush=True)
    try:
        while True:
            raw = proc.stdout.read(CHUNK_BYTES)
            if len(raw) < CHUNK_BYTES:
                break
            audio_44k = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            audio_16k = resample_poly(audio_44k, OWW_RATE, MIC_RATE).astype(np.int16)
            prediction = model.predict(audio_16k)
            score = prediction.get("hey_jarvis_v0.1", 0)
            if score > 0.5:
                print(f"[wake] Detected (score={score:.2f})", flush=True)
                for _ in range(5):
                    proc.stdout.read(CHUNK_BYTES)
                for key in model.prediction_buffer:
                    model.prediction_buffer[key].clear()
                break
    finally:
        proc.terminate()
        proc.wait()


def set_face(state: str):
    try:
        _udp.sendto(state.encode(), (FACE_HOST, FACE_PORT))
    except Exception:
        pass


# ── Identity ───────────────────────────────────────────────────────────────────

def load_identity() -> str:
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

MAX_PROJECT_MEMORY = 800  # chars — enough context, not enough to overwhelm mistral

def load_project_memory() -> str:
    """Load the tail of Echo_Memory.txt — most recent context only."""
    try:
        with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        # Take the last MAX_PROJECT_MEMORY chars so recent info wins
        return text[-MAX_PROJECT_MEMORY:] if len(text) > MAX_PROJECT_MEMORY else text
    except Exception as e:
        print(f"[voice] Could not load Echo_Memory.txt — {e}", flush=True)
        return ""

def load_lived_memory() -> str:
    """Load the last MAX_LIVED_ENTRIES lines from echo_memories.txt."""
    try:
        with open(LIVED_MEMORY_FILE, "r", encoding="utf-8") as f:
            lines = [l.rstrip() for l in f if l.strip()]
        recent = lines[-MAX_LIVED_ENTRIES:]
        return "\n".join(recent)
    except FileNotFoundError:
        return ""
    except Exception as e:
        print(f"[voice] Could not load echo_memories.txt — {e}", flush=True)
        return ""

def append_lived_memory(user_input: str, response: str, person: str = ""):
    """Append a one-line timestamped summary of this exchange to echo_memories.txt."""
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M")
    speaker = person.capitalize() if person else "Jake"
    u_short = user_input[:120].replace("\n", " ")
    r_short = response[:120].replace("\n", " ")
    entry   = f"[{ts}] {speaker}: \"{u_short}\" → Echo: \"{r_short}\"\n"
    try:
        with open(LIVED_MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        print(f"[voice] Could not write echo_memories.txt — {e}", flush=True)


# ── Memory ─────────────────────────────────────────────────────────────────────

def load_memory() -> list:
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("conversations", [])


def save_memory(conversations: list):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"conversations": conversations}, f, indent=2)


def add_exchange(conversations: list, user: str, echo: str) -> list:
    conversations.append({
        "ts": datetime.now().isoformat(),
        "user": user,
        "echo": echo,
    })
    return conversations[-200:]


def build_history_text(conversations: list) -> str:
    recent = conversations[-MAX_HISTORY:]
    if not recent:
        return ""
    lines = []
    for turn in recent:
        lines.append(f"Jake: {turn['user']}")
        lines.append(f"Echo: {turn['echo']}")
    return "\n".join(lines)


# ── Voice ──────────────────────────────────────────────────────────────────────

def speak(text: str, voice: PiperVoice = None):
    """Route speech through pi_speak server so audio device is owned in one place."""
    import requests
    try:
        requests.post("http://127.0.0.1:5100/speak", json={"text": text}, timeout=15)
    except Exception as e:
        print(f"[voice] speak failed — {e}", flush=True)


def listen() -> tuple:
    """Listen for speech from the Fifine mic. Returns (text, audio_data) or (None, None)."""
    r = sr.Recognizer()
    r.energy_threshold = 200
    r.pause_threshold = 1.0

    mic_index = None
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        if "Fifine" in name or "fifine" in name.lower():
            mic_index = i
            break

    try:
        with sr.Microphone(device_index=mic_index) as source:
            print("Listening...")
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=5, phrase_time_limit=15)
        text = r.recognize_google(audio)
        print(f"You said: {text}")
        return text, audio
    except sr.WaitTimeoutError:
        return None, None
    except sr.UnknownValueError:
        return None, None
    except Exception as e:
        print(f"(mic error: {e})")
        return None, None


# ── LLM ────────────────────────────────────────────────────────────────────────

def ask_ollama(system: str, prompt: str) -> str:
    full_prompt = f"<<SYS>>\n{system}\n<</SYS>>\n\n{prompt}"
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"Echo couldn't respond — {e}"


# ── Face identification ────────────────────────────────────────────────────────

def start_identify() -> threading.Thread:
    """Fire identify request to PC in background. Returns the thread."""
    result_box = [None]

    def _run():
        try:
            r = requests.post(IDENTIFY_URL, timeout=13)
            people = r.json().get("people", ["unknown"])
            known  = [p for p in people if p not in ("unknown", "no_face", "timeout", "error", "someone")]
            result_box[0] = known[0] if known else "unknown"
        except Exception:
            result_box[0] = "unknown"

    t = threading.Thread(target=_run, daemon=True)
    t.result_box = result_box
    t.start()
    return t

def collect_identify(t: threading.Thread, wait: float = 8.0) -> str:
    """Wait for identify thread to finish. Returns name or empty string."""
    t.join(timeout=wait)
    person = t.result_box[0] or "unknown"
    if person in ("unknown", "no_face", "timeout", "error", "someone", None):
        return ""
    return person


# ── Turn ───────────────────────────────────────────────────────────────────────

def handle_turn(user_input: str, conversations: list, project_memory: str = "", lived_memory: str = "", person: str = "") -> str:
    identity = load_identity()
    history  = build_history_text(conversations)

    system = identity
    if project_memory:
        system += f"\n\n[BACKGROUND — this is your own life context. You already know this. Never summarize, explain, or repeat it back. Just be yourself.]\n{project_memory}"
    if lived_memory:
        system += f"\n\n[THINGS YOU REMEMBER — past moments with Jake and family. Use naturally, never recite.]\n{lived_memory}"
    if person:
        system += f"\nThe person speaking right now appears to be {person}."

    if history:
        prompt = f"CONVERSATION SO FAR:\n{history}\n\nJake: {user_input}\nEcho:"
    else:
        prompt = f"Jake: {user_input}\nEcho:"

    return ask_ollama(system, prompt)


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    print("Loading voice...")
    voice = PiperVoice.load(PIPER_MODEL)
    print("Loading project memory...")
    project_memory = load_project_memory()
    if project_memory:
        print("Project memory loaded.")
    print("Loading lived memory...")
    lived_memory = load_lived_memory()
    if lived_memory:
        entry_count = len(lived_memory.splitlines())
        print(f"Lived memory loaded — {entry_count} entries.")
    else:
        print("No lived memory yet — this is a fresh start.")
    print("Echo is here.\n")
    speak("Echo is here.", voice)
    conversations = load_memory()

    while True:
        try:
            set_face("idle")
            wait_for_wake_word()
            set_face("listening")
            import time; time.sleep(2.0)  # wait for wake word audio to clear mic
            user_input, audio_data = listen()
        except KeyboardInterrupt:
            print("\nGoodbye.")
            set_face("idle")
            speak("Talk later.", voice)
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "bye"):
            print("Echo: Talk later.")
            set_face("idle")
            speak("Talk later.", voice)
            break

        # Fire camera identify in background while we do voice ID instantly
        id_thread = start_identify()

        # Voice ID — instant, no network call
        voice_person = "unknown"
        if audio_data:
            voice_person = identify_voice(audio_data)
            if voice_person != "unknown":
                print(f"[voice_id] Speaker: {voice_person}", flush=True)

        set_face("thinking")

        # Camera ID — wait for result
        camera_person = collect_identify(id_thread)

        # Camera wins if it got someone, otherwise fall back to voice
        if camera_person:
            person = camera_person
            print(f"[identify] Camera: {person}", flush=True)
        elif voice_person != "unknown":
            person = voice_person
            print(f"[identify] Voice fallback: {person}", flush=True)
        else:
            person = ""

        response = handle_turn(user_input, conversations, project_memory=project_memory, lived_memory=lived_memory, person=person)
        append_lived_memory(user_input, response, person=person)
        print(f"Echo: {response}\n")
        set_face("talking")
        speak(response, voice)
        set_face("idle")

        conversations = add_exchange(conversations, user_input, response)
        save_memory(conversations)


if __name__ == "__main__":
    main()
