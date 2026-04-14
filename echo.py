"""
echo.py
Echo — runtime controller.
Handles face/voice sync, LLM interaction, and modular memory state.
"""

import io
import os
import wave
import subprocess
import requests
import speech_recognition as sr
import face
from piper import PiperVoice
from datetime import datetime

from echo_memory import (
    initialize_echo_state,
    append_episodic_event,
    update_emotional_state,
    refresh_echo_state_after_update,
    load_recent_episodic_memory,
)

# ── Config ─────────────────────────────────────────────────────────────────────

PIPER_MODEL  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "en_US-lessac-medium.onnx")
FFPLAY       = r"C:\Users\jrsrl\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffplay.exe"
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:7b"
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "identity.md")
MAX_HISTORY  = 20

# ── Conversation history (in-session only) ─────────────────────────────────────

def load_identity() -> str:
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def build_history_text(conversations: list) -> str:
    recent = conversations[-MAX_HISTORY:]
    if not recent:
        return ""
    lines = []
    for turn in recent:
        lines.append(f"Jake: {turn['user']}")
        lines.append(f"Echo: {turn['echo']}")
    return "\n".join(lines)

# ── EchoState → prompt context ─────────────────────────────────────────────────

def build_state_context(state: dict) -> str:
    """Convert EchoState into a readable context block for the LLM prompt."""
    emotion   = state["emotion"].get("current", "warm")
    baseline  = state["emotion"].get("baseline", "warm")
    episodes  = state["episodic"][-5:]  # last 5 events only

    lines = [f"Current emotional state: {emotion} (baseline: {baseline})"]

    if episodes:
        lines.append("Recent memory:")
        for e in episodes:
            ts  = e.get("timestamp", "")[:10]
            evt = e.get("event", "")
            lines.append(f"  [{ts}] {evt}")

    return "\n".join(lines)

# ── LLM ────────────────────────────────────────────────────────────────────────

def ask_ollama(system: str, prompt: str) -> str:
    full_prompt = f"<<SYS>>\n{system}\n<</SYS>>\n\n{prompt}"
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": full_prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"(Echo couldn't respond — {e})"

def handle_turn(user_input: str, conversations: list, state: dict) -> str:
    identity     = load_identity()
    history      = build_history_text(conversations)
    state_ctx    = build_state_context(state)

    system = f"{identity}\n\n{state_ctx}"

    if history:
        prompt = f"CONVERSATION SO FAR:\n{history}\n\nJake: {user_input}\nEcho:"
    else:
        prompt = f"Jake: {user_input}\nEcho:"

    return ask_ollama(system, prompt)

# ── Voice ──────────────────────────────────────────────────────────────────────

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

# ── Emotion inference ──────────────────────────────────────────────────────────

def infer_emotion(user_input: str, response: str) -> str | None:
    """Simple keyword-based emotion update. Returns new emotion or None."""
    text = (user_input + " " + response).lower()
    if any(w in text for w in ["hardware", "arrived", "working", "built", "done", "success"]):
        return "excited"
    if any(w in text for w in ["error", "broken", "failed", "can't", "problem"]):
        return "concerned"
    if any(w in text for w in ["thank", "love", "miss", "family", "judy"]):
        return "warm"
    if any(w in text for w in ["interesting", "wonder", "what if", "how does", "curious"]):
        return "curious"
    return None

# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    print("Loading voice...")
    voice = PiperVoice.load(PIPER_MODEL)

    print("Loading Echo state...")
    state = initialize_echo_state()
    print(f"  Emotion  : {state['emotion']['current']}")
    print(f"  Episodes : {len(state['episodic'])} events in memory")

    face.start_face()
    print("Echo is here.\n")

    conversations = []

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
            append_episodic_event("Session ended", context="Jake said bye")
            break

        face.thinking()
        response = handle_turn(user_input, conversations, state)
        print(f"Echo: {response}\n")
        face.talking()
        speak(response, voice)
        face.idle()

        # Update conversation history
        conversations.append({
            "ts":   datetime.now().isoformat(),
            "user": user_input,
            "echo": response,
        })
        conversations = conversations[-200:]

        # Update memory state
        append_episodic_event(
            f"Talked with Jake: {user_input[:80]}",
            context=f"Echo responded: {response[:80]}"
        )

        new_emotion = infer_emotion(user_input, response)
        if new_emotion and new_emotion != state["emotion"]["current"]:
            update_emotional_state(new_emotion)

        state = refresh_echo_state_after_update(state)


if __name__ == "__main__":
    main()
