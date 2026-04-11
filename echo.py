"""
echo.py
Echo — a simple persistent companion AI.
Talks to Ollama, remembers conversations, stays in character.
"""

import io
import json
import os
import wave
import subprocess
import requests
import speech_recognition as sr
import face
from piper import PiperVoice
from datetime import datetime

PIPER_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "en_US-lessac-medium.onnx")
FFPLAY      = r"C:\Users\jrsrl\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffplay.exe"

# ── Config ─────────────────────────────────────────────────────────────────────

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:7b"
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "identity.md")
MEMORY_FILE   = os.path.join(os.path.dirname(__file__), "memory.json")
MAX_HISTORY   = 20   # turns to keep in context


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
    # Keep only the last 200 exchanges on disk
    return conversations[-200:]


def build_history_text(conversations: list) -> str:
    """Format recent conversation history for the prompt."""
    recent = conversations[-MAX_HISTORY:]
    if not recent:
        return ""
    lines = []
    for turn in recent:
        lines.append(f"Jake: {turn['user']}")
        lines.append(f"Echo: {turn['echo']}")
    return "\n".join(lines)


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
        return f"(Echo couldn't respond — {e})"


# ── Turn ───────────────────────────────────────────────────────────────────────

def handle_turn(user_input: str, conversations: list) -> str:
    identity = load_identity()
    history  = build_history_text(conversations)

    system = identity

    if history:
        prompt = f"CONVERSATION SO FAR:\n{history}\n\nJake: {user_input}\nEcho:"
    else:
        prompt = f"Jake: {user_input}\nEcho:"

    response = ask_ollama(system, prompt)
    return response


# ── Main loop ──────────────────────────────────────────────────────────────────

def listen() -> str | None:
    try:
        user_input = input("You: ").strip()
        return user_input if user_input else None
    except (EOFError, KeyboardInterrupt):
        raise KeyboardInterrupt


def speak(text: str, voice: PiperVoice):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        voice.synthesize_wav(text, wav)
    buf.seek(0)
    proc = subprocess.Popen(
        [FFPLAY, "-nodisp", "-autoexit", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.communicate(input=buf.read())


def main():
    print("Loading voice...")
    voice = PiperVoice.load(PIPER_MODEL)
    face.start_face()
    print("Echo is here.\n")
    conversations = load_memory()

    while True:
        try:
            face.idle()
            user_input = listen()
            if not user_input:
                continue
        except KeyboardInterrupt:
            print("\nGoodbye.")
            break

        if user_input.lower() in ("quit", "exit", "bye"):
            print("Echo: Talk later.")
            speak("Talk later.", voice)
            break

        face.thinking()
        response = handle_turn(user_input, conversations)
        print(f"Echo: {response}\n")
        face.talking()
        speak(response, voice)
        face.idle()

        conversations = add_exchange(conversations, user_input, response)
        save_memory(conversations)


if __name__ == "__main__":
    main()
