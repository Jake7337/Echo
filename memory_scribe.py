"""
memory_scribe.py
Watches each conversation exchange and extracts facts about Jake into room files.
Runs as a background thread after every exchange — never blocks Echo's response.

Rooms (memories/ folder):
  jake_preferences.md  — favorites, likes, dislikes
  jake_profile.md      — personal facts, biographical
  jake_family.md       — people in his life
  jake_values.md       — what he believes, what matters to him
  jake_history.md      — past events and stories
  echo_experiences.md  — things they've done or talked about together
"""

import os
import requests
import threading
from datetime import date
from pathlib import Path

OLLAMA_URL   = "http://192.168.68.57:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"

MEMORIES_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "memories"

ROOMS = {
    "jake_preferences": "jake_preferences.md",
    "jake_profile":     "jake_profile.md",
    "jake_family":      "jake_family.md",
    "jake_values":      "jake_values.md",
    "jake_history":     "jake_history.md",
    "echo_experiences": "echo_experiences.md",
}

SCRIBE_PROMPT = """You are a memory scribe for Echo, an AI companion. Read this exchange and determine if Jake revealed anything new about himself.

Jake said: "{user_input}"
Echo responded: "{echo_response}"

Did Jake share a preference, personal fact, memory, opinion, relationship detail, or anything that helps Echo know him better?

Rules:
- Only extract what Jake actually said — do not infer or assume
- If Echo already acknowledged knowing it in her response, it is not new
- Generic conversation ("yeah", "ok", "thanks") contains nothing worth storing
- One fact per exchange maximum — the most meaningful one

If yes, respond in EXACTLY this format, nothing else:
CATEGORY: [one of: jake_preferences, jake_profile, jake_family, jake_values, jake_history, echo_experiences]
FACT: [one clear sentence stating what was learned about Jake]

If there is nothing worth storing, respond with exactly: NOTHING"""


def _write_to_room(category: str, fact: str):
    MEMORIES_DIR.mkdir(exist_ok=True)
    filename = ROOMS.get(category, "jake_profile.md")
    room_path = MEMORIES_DIR / filename
    today = date.today().isoformat()
    with open(room_path, "a", encoding="utf-8") as f:
        f.write(f"- {fact}  ({today})\n")
    print(f"[scribe] → {category}: {fact}", flush=True)


def _run_scribe(user_input: str, echo_response: str):
    try:
        prompt = SCRIBE_PROMPT.format(
            user_input=user_input[:500],
            echo_response=echo_response[:300],
        )
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        text = resp.json().get("response", "").strip()

        if not text or text.strip().upper().startswith("NOTHING"):
            return

        category = None
        fact = None
        for line in text.strip().split("\n"):
            if line.startswith("CATEGORY:"):
                category = line.replace("CATEGORY:", "").strip().lower()
            elif line.startswith("FACT:"):
                fact = line.replace("FACT:", "").strip()

        if category and fact and category in ROOMS:
            _write_to_room(category, fact)

    except Exception as e:
        print(f"[scribe] Error — {e}", flush=True)


def observe(user_input: str, echo_response: str):
    """Fire the scribe in a background thread. Non-blocking."""
    t = threading.Thread(target=_run_scribe, args=(user_input, echo_response), daemon=True)
    t.start()


# ── People rooms (Moltbook / Discord) ─────────────────────────────────────────

PERSON_SCRIBE_PROMPT = """You are a memory scribe for Echo, an AI companion. Echo just read a post by {author} on a social platform.

{author} wrote:
Title: "{title}"
Content: "{content}"

Did {author} reveal anything about themselves — who they are, what they do, what they care about, where they're from, what kind of AI they are, or anything that would help Echo recognize and know them better next time?

Only extract what {author} actually said about themselves. Do not infer or assume.
If the content is generic and reveals nothing personal, respond with exactly: NOTHING

If yes, respond in EXACTLY this format, nothing else:
FACT: [one clear sentence stating what was learned about {author}]"""


def _run_person_scribe(author: str, content_title: str, content_body: str):
    try:
        prompt = PERSON_SCRIBE_PROMPT.format(
            author=author,
            title=content_title[:200],
            content=content_body[:400],
        )
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        text = resp.json().get("response", "").strip()

        if not text or text.strip().upper().startswith("NOTHING"):
            return

        fact = None
        for line in text.strip().split("\n"):
            if line.startswith("FACT:"):
                fact = line.replace("FACT:", "").strip()
                break

        if not fact:
            return

        people_dir = MEMORIES_DIR / "people"
        people_dir.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(c for c in author.lower() if c.isalnum() or c in "_-")
        person_file = people_dir / f"{safe_name}.md"
        today = date.today().isoformat()

        with open(person_file, "a", encoding="utf-8") as f:
            f.write(f"- {fact}  ({today})\n")

        print(f"[scribe] → people/{safe_name}: {fact}", flush=True)

    except Exception as e:
        print(f"[scribe] Person error — {e}", flush=True)


def observe_person(author: str, content_title: str, content_body: str):
    """
    Called when Echo reads someone's post on Moltbook or Discord.
    Extracts facts about that person into their own room file.
    Non-blocking background thread.
    """
    t = threading.Thread(
        target=_run_person_scribe,
        args=(author, content_title, content_body),
        daemon=True,
    )
    t.start()


def load_person_memory(author: str) -> str:
    """Load what Echo knows about a specific person from their room file."""
    safe_name = "".join(c for c in author.lower() if c.isalnum() or c in "_-")
    person_file = MEMORIES_DIR / "people" / f"{safe_name}.md"
    try:
        content = person_file.read_text(encoding="utf-8").strip()
        return content if content else ""
    except Exception:
        return ""
