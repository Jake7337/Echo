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
    retrieve_relevant_events,
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
# — Retrieval Trigger Logic ————————————————————————————————

RETRIEVAL_TRIGGERS = [
    "when did", "when was", "when were",
    "have i ever", "did i ever",
    "last time", "first time",
    "what happened when",
    "remind me what", "remind me when",
    "how did i feel", "how was i feeling",
    "who did i", "who was i with",
    "did you ever", "have you ever"
]

KNOWN_PEOPLE = ["lydea", "rachael", "judy", "john", "chance"]

def should_trigger_retrieval(user_input: str) -> bool:
    text = user_input.lower()

    if any(phrase in text for phrase in RETRIEVAL_TRIGGERS):
        return True

    if any(name in text for name in KNOWN_PEOPLE):
        return True

    if "i remember" in text or "do you remember" in text:
        return True

    return False


def format_retrieved_events(events):
    if not events:
        return ""
    lines = ["Relevant past events:"]
    for e in events:
        lines.append(f"- {e['summary']} ({e['type']}, {e['timestamp']})")
    return "\n".join(lines)

# ── EchoState → prompt context ─────────────────────────────────────────────────

def condense_rules_for_prompt(rules: dict) -> str:
    """
    Extract the most important rules into a short LLM-friendly block.
    Pulls from core_rules, prohibitions, fallback_behaviors, and
    one key item per interaction_rules category.
    Kept short deliberately — Pi performance matters.
    """
    lines = ["RULES:"]

    # Top 5 core rules
    for rule in rules.get("core_rules", [])[:5]:
        lines.append(f"- {rule}")

    # Top 5 prohibitions
    lines.append("NEVER:")
    for rule in rules.get("prohibitions", [])[:5]:
        lines.append(f"- {rule}")

    # Top 3 fallbacks
    lines.append("IF UNSURE:")
    for rule in rules.get("fallback_behaviors", [])[:3]:
        lines.append(f"- {rule}")

    # One key item per interaction_rules category
    interaction = rules.get("interaction_rules", {})
    tone_rules = interaction.get("tone", [])
    if tone_rules:
        lines.append(f"TONE: {tone_rules[0]}")

    return "\n".join(lines)


def condense_metacognition_for_prompt(meta: dict) -> str:
    """
    Extract the load-bearing metacognition principles into a short prompt block.
    3 reasoning principles, 2 uncertainty rules, 1 each from
    continuity, memory, and self-reflection. ~8 lines total.
    """
    lines = ["HOW ECHO THINKS:"]

    for rule in meta.get("reasoning_principles", [])[:3]:
        lines.append(f"- {rule}")

    for rule in meta.get("uncertainty_handling", [])[:2]:
        lines.append(f"- {rule}")

    continuity = meta.get("continuity_logic", [])
    if continuity:
        lines.append(f"- {continuity[0]}")

    memory = meta.get("memory_logic", [])
    if memory:
        lines.append(f"- {memory[0]}")

    reflection = meta.get("self_reflection", [])
    if reflection:
        lines.append(f"- {reflection[0]}")

    return "\n".join(lines)


def condense_episodic_memory_for_prompt(events: list) -> str:
    """
    Summarize the most important recent episodic events for prompt injection.
    Prioritizes high-importance events, then medium. Max 5 entries, 1 line each.
    """
    high   = [e for e in events if e.get("importance") == "high"]
    medium = [e for e in events if e.get("importance") == "medium"]
    pool   = (high + medium)[-5:]

    if not pool:
        return ""

    lines = ["Recent events:"]
    for e in pool:
        ts      = e.get("timestamp", "")[:10]
        summary = e.get("summary", "")
        emotion = e.get("emotion", "")
        tag     = f" [{emotion}]" if emotion else ""
        lines.append(f"  [{ts}] {summary}{tag}")

    return "\n".join(lines)


def build_state_context(state: dict) -> str:
    """
    Build the runtime context block injected into every LLM prompt.
    Order: emotion → rules → metacognition → episodic continuity.
    This is Echo's complete cognitive stack at prompt time.
    """
    emotion  = state["emotion"].get("current", "warm")
    baseline = state["emotion"].get("baseline", "warm")

    lines = [f"Current emotional state: {emotion} (baseline: {baseline})"]

    # Condensed behavioral rules
    if state.get("rules"):
        lines.append("")
        lines.append(condense_rules_for_prompt(state["rules"]))

    # Condensed reasoning principles
    if state.get("meta"):
        lines.append("")
        lines.append(condense_metacognition_for_prompt(state["meta"]))

    # Condensed episodic continuity — high/medium importance only
    episodic_summary = condense_episodic_memory_for_prompt(state.get("episodic", []))
    if episodic_summary:
        lines.append("")
        lines.append(episodic_summary)

    return "\n".join(lines)

# ── Memory retrieval ───────────────────────────────────────────────────────

def retrieve_memory(query: str) -> list:
    """Retrieve relevant episodic events for a natural language query."""
    return retrieve_relevant_events(query)


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
    print(f"  Rules    : {len(state.get('rules', {}).get('core_rules', []))} core rules loaded")

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
            append_episodic_event("Session ended — Jake said bye", event_type="system", importance="low")
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
            event_type="interaction",
            importance="low"
        )

        new_emotion = infer_emotion(user_input, response)
        if new_emotion and new_emotion != state["emotion"]["current"]:
            update_emotional_state(new_emotion)

        state = refresh_echo_state_after_update(state)


if __name__ == "__main__":
    main()
