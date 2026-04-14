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


VALID_TYPES      = {"interaction", "insight", "emotional_shift", "milestone", "reflection", "system"}
VALID_IMPORTANCE = {"low", "medium", "high"}

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

def retrieve_episodic_by_type(event_type: str, limit: int = 10) -> list:
    """Retrieve episodic events filtered by type."""
    all_events = load_recent_episodic_memory(limit=200)
    return [e for e in all_events if e.get("type") == event_type][-limit:]

def retrieve_episodic_by_importance(importance: str = "high", limit: int = 10) -> list:
    """Retrieve episodic events filtered by importance level."""
    all_events = load_recent_episodic_memory(limit=200)
    return [e for e in all_events if e.get("importance") == importance][-limit:]

# ── Retrieval heuristics ───────────────────────────────────────────────────────

# Keywords that signal what kind of event to look for
_PERSON_SIGNALS    = ["said", "talked", "spoke", "heard", "told", "asked", "mentioned"]
_SELF_SIGNALS      = ["i learned", "i knew", "my first", "when did i", "do i remember",
                      "have i", "was i", "did i"]
_FEELING_SIGNALS   = ["feel", "felt", "emotion", "mood", "excited", "nervous", "happy",
                      "sad", "worried", "warm", "curious", "proud"]
_SYSTEM_SIGNALS    = ["camera", "memory", "hardware", "chassis", "install", "update",
                      "system", "started", "went live", "built", "arrived"]

def _importance_rank(event: dict) -> int:
    """Convert importance string to sort key. Higher = more important."""
    return {"high": 3, "medium": 2, "low": 1}.get(event.get("importance", "low"), 1)

def _keyword_score(event: dict, keywords: list) -> int:
    """Count how many keywords appear in the event summary."""
    summary = event.get("summary", "").lower()
    return sum(1 for kw in keywords if kw in summary)

def _score_event(event: dict, query_lower: str, type_boost: list) -> int:
    """
    Score a single event for relevance to a query.
    Combines importance, type match, and keyword overlap.
    """
    score = _importance_rank(event)

    # Boost for matching target types
    if event.get("type") in type_boost:
        score += 2

    # Keyword overlap with the query
    summary_words = event.get("summary", "").lower().split()
    query_words   = query_lower.split()
    overlap       = len(set(summary_words) & set(query_words))
    score += overlap

    return score

def retrieve_relevant_events(query: str, max_results: int = 3) -> list:
    """
    Retrieve the most relevant episodic events for a given query.

    Heuristic rules:
    - Person mention     → search interaction events
    - Self-reference     → search insight + milestone
    - Feeling mention    → search emotional_shift
    - System mention     → search system events
    - Vague query        → return recent high-importance events

    Always prefers: high importance → recent → keyword match.

    Args:
        query:       Natural language query string
        max_results: Max events to return (default 3, keep low for Pi)

    Returns:
        List of matching event dicts, sorted by relevance score descending.
    """
    if not query:
        return retrieve_episodic_by_importance("high", limit=max_results)

    q = query.lower()
    all_events = load_recent_episodic_memory(limit=200)

    # Determine which event types to boost based on query signals
    type_boost = []

    if any(sig in q for sig in _PERSON_SIGNALS):
        type_boost.append("interaction")

    if any(sig in q for sig in _SELF_SIGNALS):
        type_boost += ["insight", "milestone"]

    if any(sig in q for sig in _FEELING_SIGNALS):
        type_boost.append("emotional_shift")

    if any(sig in q for sig in _SYSTEM_SIGNALS):
        type_boost.append("system")

    # Vague query — no signals matched, return recent high-importance
    if not type_boost:
        high = [e for e in all_events if e.get("importance") == "high"]
        return high[-max_results:]

    # Score all events and sort
    scored = sorted(
        all_events,
        key=lambda e: _score_event(e, q, type_boost),
        reverse=True
    )

    # Filter out zero-score low-importance events to avoid noise
    relevant = [e for e in scored if _score_event(e, q, type_boost) > 1]

    return relevant[:max_results]


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

def append_episodic_event(
    summary: str,
    event_type: str = "interaction",
    emotion: str = "",
    importance: str = "low"
):
    """
    Append a structured event to episodic_memory.jsonl.
    This file is append-only — never overwritten.

    Args:
        summary:    Short description of what happened
        event_type: interaction | insight | emotional_shift | milestone | reflection | system
        emotion:    Optional emotional tag
        importance: low | medium | high
    """
    if event_type not in VALID_TYPES:
        event_type = "interaction"
    if importance not in VALID_IMPORTANCE:
        importance = "low"

    entry = {
        "timestamp":  datetime.now().isoformat(),
        "type":       event_type,
        "summary":    summary,
        "importance": importance,
    }
    if emotion:
        entry["emotion"] = emotion

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
