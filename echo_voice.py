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
import subprocess
import requests
import speech_recognition as sr
from piper import PiperVoice
from datetime import datetime


# ── Config ─────────────────────────────────────────────────────────────────────

OLLAMA_URL    = "http://192.168.68.65:11434/api/generate"
OLLAMA_MODEL  = "mistral:7b"
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "identity.md")
MEMORY_FILE   = os.path.join(os.path.dirname(__file__), "memory.json")
MAX_HISTORY   = 20

MIC_CARD      = 3   # Fifine Microphone
SPEAKER_CARD  = 2   # USB AUDIO
PIPER_MODEL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "en_US-lessac-medium.onnx")


# ── Identity ───────────────────────────────────────────────────────────────────

def load_identity() -> str:
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


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
    """Speak text through USB speakers using Piper TTS."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        voice.synthesize_wav(text, wav)
    buf.seek(0)
    aplay = subprocess.Popen(
        ["aplay", "-D", "plughw:2,0", "-"],
        stdin=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    aplay.communicate(input=buf.read())


def listen() -> str | None:
    """Listen for speech from the Fifine mic. Returns text or None."""
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
        return text
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except Exception as e:
        print(f"(mic error: {e})")
        return None


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


# ── Turn ───────────────────────────────────────────────────────────────────────

def handle_turn(user_input: str, conversations: list) -> str:
    identity = load_identity()
    history  = build_history_text(conversations)

    if history:
        prompt = f"CONVERSATION SO FAR:\n{history}\n\nJake: {user_input}\nEcho:"
    else:
        prompt = f"Jake: {user_input}\nEcho:"

    return ask_ollama(identity, prompt)


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    print("Loading voice...")
    voice = PiperVoice.load(PIPER_MODEL)
    print("Echo is here.\n")
    speak("Echo is here.", voice)
    conversations = load_memory()

    while True:
        try:
            user_input = listen()
        except KeyboardInterrupt:
            print("\nGoodbye.")
            speak("Talk later.", voice)
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "bye"):
            print("Echo: Talk later.")
            speak("Talk later.", voice)
            break

        response = handle_turn(user_input, conversations)
        print(f"Echo: {response}\n")
        speak(response, voice)

        conversations = add_exchange(conversations, user_input, response)
        save_memory(conversations)


if __name__ == "__main__":
    main()
