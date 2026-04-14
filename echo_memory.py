"""
echo_memory.py
Echo's modular memory manager.

Architecture:
  /memory/identity_core.json       — read-only identity
  /memory/procedural_rules.json    — rules and boundaries
  /memory/metacognition.json       — how Echo thinks about thinking
  /memory/emotional_state.json     — current + baseline emotion
  /memory/episodic_memory.jsonl    — append-only event log

Usage:
  state = initialize_echo_state()
  append_episodic_event("Something happened", emotion="curious")
  update_emotional_state({"current": "excited"})
  state = refresh_echo_state_after_update(state)
"""

import json
import os
from datetime import datetime

# ── File paths ─────────────────────────────────────────────────────────────────

MEMORY_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory")
IDENTITY_FILE = os.path.join(MEMORY_DIR, "identity_core.json")
RULES_FILE    = os.path.join(MEMORY_DIR, "procedural_rules.json")
META_FILE     = os.path.join(MEMORY_DIR, "metacognition.json")
EMOTION_FILE  = os.path.join(MEMORY_DIR, "emotional_state.json")
EPISODIC_FILE = os.path.join(MEMORY_DIR, "episodic_memory.jsonl")


# ── Validation helpers ─────────────────────────────────────────────────────────

def _require_keys(data: dict, keys: list, source: str):
    """Warn if expected keys are missing. Non-fatal — Echo keeps running."""
    for key in keys:
        if key not in data:
            print(f"[memory] Warning: '{key}' missing from {source}")


# ── Loaders ────────────────────────────────────────────────────────────────────

def load_identity_core() -> dict:
    """
    Load Echo's core identity. Read-only at runtime.
    Contains name, role, personality, relationships, platforms.
    """
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    _require_keys(data, ["name", "role", "personality", "relationships"], "identity_core.json")
    return data


def load_procedural_rules() -> dict:
    """
    Load communication rules and behavioral boundaries.
    Can be updated explicitly via save_procedural_rules().
    """
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    _require_keys(data, ["communication", "boundaries"], "procedural_rules.json")
    return data


def load_metacognition() -> dict:
    """
    Load Echo's self-awareness model — continuity, update rules, interpretation flags.
    """
    with open(META_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    _require_keys(data, ["continuity", "self_update"], "metacognition.json")
    return data


def load_emotional_state() -> dict:
    """
    Load Echo's current emotional state — current mood, baseline, triggers.
    Updated after each interaction.
    """
    with open(EMOTION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    _require_keys(data, ["baseline", "current"], "emotional_state.json")
    return data


def load_recent_episodic_memory(limit: int = 50) -> list:
    """
    Load the most recent episodic events from the append-only log.
    Returns up to `limit` events as a list of dicts.
    """
    if not os.path.exists(EPISODIC_FILE):
        return []
    events = []
    with open(EPISODIC_FILE, "r", encoding="utf-8") as f:
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
    """
    Build and return the full EchoState object.
    Called once at startup.

    Returns:
        EchoState = {
            "identity": {...},
            "rules":    {...},
            "meta":     {...},
            "emotion":  {...},
            "episodic": [...]
        }
    """
    return {
        "identity": load_identity_core(),
        "rules":    load_procedural_rules(),
        "meta":     load_metacognition(),
        "emotion":  load_emotional_state(),
        "episodic": load_recent_episodic_memory(),
    }


# ── Updaters ───────────────────────────────────────────────────────────────────

def append_episodic_event(event: str, emotion: str = "", context: str = ""):
    """
    Append a single event to episodic_memory.jsonl.
    This file is append-only — never overwritten.

    Args:
        event:   Description of what happened
        emotion: Optional emotional tag for this event
        context: Optional extra detail
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event":     event,
    }
    if emotion:
        entry["emotion"] = emotion
    if context:
        entry["context"] = context

    with open(EPISODIC_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def update_emotional_state(new_state: dict):
    """
    Update emotional_state.json with new values.
    Always stamps last_updated.

    Args:
        new_state: dict with at minimum {"current": "emotion_name"}
                   Can also include "baseline" or "triggers" updates.

    Example:
        update_emotional_state({"current": "excited"})
    """
    state = load_emotional_state()
    state.update(new_state)
    state["last_updated"] = datetime.now().isoformat()
    with open(EMOTION_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def save_procedural_rules(new_rules: dict):
    """
    Overwrite procedural_rules.json with new rules.
    Call this explicitly only — never called automatically at runtime.

    Args:
        new_rules: Complete replacement rules dict
    """
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(new_rules, f, indent=2)


# ── State refresh ──────────────────────────────────────────────────────────────

def refresh_echo_state_after_update(state: dict) -> dict:
    """
    Re-load the mutable parts of EchoState after an update.
    Identity and rules are stable — only emotion and episodic are refreshed.

    Args:
        state: The current EchoState object

    Returns:
        Updated EchoState with fresh emotion and episodic data
    """
    state["emotion"]  = load_emotional_state()
    state["episodic"] = load_recent_episodic_memory()
    return state


# ── CLI test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    state = initialize_echo_state()
    print("Echo memory loaded.")
    print(f"  Name     : {state['identity']['name']}")
    print(f"  Location : {state['identity'].get('location', 'unknown')}")
    print(f"  Emotion  : {state['emotion']['current']} (baseline: {state['emotion']['baseline']})")
    print(f"  Episodes : {len(state['episodic'])} events loaded")
    print(f"  Rules    : {list(state['rules'].keys())}")
    print(f"  Meta     : {list(state['meta'].keys())}")
