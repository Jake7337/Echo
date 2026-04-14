"""
echo_memory.py
Echo's structured memory system.
Load → use → update.
"""

import json
import os
from datetime import datetime

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory")

IDENTITY_FILE   = os.path.join(MEMORY_DIR, "identity_core.json")
RULES_FILE      = os.path.join(MEMORY_DIR, "procedural_rules.json")
META_FILE       = os.path.join(MEMORY_DIR, "metacognition.json")
EMOTION_FILE    = os.path.join(MEMORY_DIR, "emotional_state.json")
EPISODIC_FILE   = os.path.join(MEMORY_DIR, "episodic_memory.jsonl")

# ── Loaders ────────────────────────────────────────────────────────────────────

def load_identity_core() -> dict:
    with open(IDENTITY_FILE) as f:
        return json.load(f)

def load_procedural_rules() -> dict:
    with open(RULES_FILE) as f:
        return json.load(f)

def load_metacognition() -> dict:
    with open(META_FILE) as f:
        return json.load(f)

def load_emotional_state() -> dict:
    with open(EMOTION_FILE) as f:
        return json.load(f)

def load_recent_episodic_memory(limit: int = 50) -> list:
    if not os.path.exists(EPISODIC_FILE):
        return []
    events = []
    with open(EPISODIC_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events[-limit:]

# ── Initializer ────────────────────────────────────────────────────────────────

def initialize_echo_state() -> dict:
    return {
        "identity": load_identity_core(),
        "rules":    load_procedural_rules(),
        "meta":     load_metacognition(),
        "emotion":  load_emotional_state(),
        "episodic": load_recent_episodic_memory(),
    }

# ── Updaters ───────────────────────────────────────────────────────────────────

def update_emotional_state(new_emotion: str):
    state = load_emotional_state()
    state["current"] = new_emotion
    state["last_updated"] = datetime.now().isoformat()
    with open(EMOTION_FILE, "w") as f:
        json.dump(state, f, indent=2)

def append_episodic_event(event: str, emotion: str = "", context: str = ""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
    }
    if emotion:
        entry["emotion"] = emotion
    if context:
        entry["context"] = context
    with open(EPISODIC_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

def save_procedural_rules(new_rules: dict):
    with open(RULES_FILE, "w") as f:
        json.dump(new_rules, f, indent=2)

# ── Refresh ────────────────────────────────────────────────────────────────────

def refresh_echo_state_after_update(state: dict) -> dict:
    state["emotion"]  = load_emotional_state()
    state["episodic"] = load_recent_episodic_memory()
    return state


if __name__ == "__main__":
    state = initialize_echo_state()
    print(f"Echo state loaded.")
    print(f"  Identity : {state['identity']['name']} — {state['identity']['location']}")
    print(f"  Emotion  : {state['emotion']['current']} (baseline: {state['emotion']['baseline']})")
    print(f"  Episodes : {len(state['episodic'])} events loaded")
