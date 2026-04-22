"""
discord_echo.py
Echo on Discord — same brain, same memory, new room.
"""

import json
import os
import time
import discord
import requests
from datetime import datetime
from pathlib import Path
import memory_scribe

# ── Config ─────────────────────────────────────────────────────────────────────

TOKEN_FILE          = os.path.join(os.path.dirname(__file__), "Echo Discord Token.txt")
IDENTITY_FILE       = os.path.join(os.path.dirname(__file__), "identity.md")
MEMORY_FILE         = os.path.join(os.path.dirname(__file__), "memory.json")
PROJECT_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "Echo_Memory.txt")
LIVED_MEMORY_FILE   = os.path.join(os.path.dirname(__file__), "echo_memories.txt")
MEMORIES_DIR        = Path(os.path.dirname(__file__)) / "memories"
OLLAMA_URL          = "http://localhost:11434/api/generate"
OLLAMA_MODEL        = "llama3.1:8b"
MAX_HISTORY         = 20
MAX_PROJECT_MEMORY  = 800
MAX_LIVED_ENTRIES   = 100
USER_COOLDOWN_SEC   = 8   # ignore repeat messages from same user within this window

_last_response_ts: dict = {}  # user_id → timestamp

with open(TOKEN_FILE, "r") as f:
    TOKEN = f.read().strip()

# ── Identity & Memory ──────────────────────────────────────────────────────────

def load_identity() -> str:
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def load_project_memory() -> str:
    try:
        with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        return text[-MAX_PROJECT_MEMORY:] if len(text) > MAX_PROJECT_MEMORY else text
    except Exception:
        return ""

def load_rooms() -> str:
    """Load all memory room files — same knowledge base voice Echo uses."""
    if not MEMORIES_DIR.exists():
        return ""
    blocks = []
    for md_file in sorted(MEMORIES_DIR.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8").strip()
            if content:
                blocks.append(f"[{md_file.stem}]\n{content}")
        except Exception:
            pass
    return "\n\n".join(blocks)

def load_lived_memory() -> str:
    try:
        with open(LIVED_MEMORY_FILE, "r", encoding="utf-8") as f:
            lines = [l.rstrip() for l in f if l.strip()]
        return "\n".join(lines[-MAX_LIVED_ENTRIES:])
    except Exception:
        return ""

def load_memory() -> list:
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("conversations", [])

def save_memory(conversations: list):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"conversations": conversations}, f, indent=2)

def add_exchange(conversations: list, speaker: str, user: str, echo: str) -> list:
    conversations.append({
        "ts": datetime.now().isoformat(),
        "speaker": speaker,
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
        lines.append(f"{turn.get('speaker', 'someone')}: {turn['user']}")
        lines.append(f"Echo: {turn['echo']}")
    return "\n".join(lines)

# ── LLM ────────────────────────────────────────────────────────────────────────

def clean_response(text: str) -> str:
    """Strip anything after Echo starts replaying the conversation."""
    import re
    # Cut off at the first line that looks like a new speaker turn
    lines = text.split("\n")
    output = []
    for line in lines:
        if re.match(r"^\w[\w\s]*:", line) and output:
            break
        output.append(line)
    return "\n".join(output).strip()

def ask_ollama(system: str, prompt: str) -> str:
    full_prompt = f"<<SYS>>\n{system}\n<</SYS>>\n\n{prompt}"
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": full_prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        return clean_response(raw)
    except Exception as e:
        return f"(Echo couldn't respond — {e})"

def handle_turn(speaker: str, user_input: str, conversations: list) -> str:
    identity       = load_identity()
    project_memory = load_project_memory()
    lived_memory   = load_lived_memory()
    rooms          = load_rooms()
    history        = build_history_text(conversations)

    system = identity
    if project_memory:
        system += f"\n\n[BACKGROUND — this is your own life context. You already know this. Never summarize, explain, or repeat it back. Just be yourself.]\n{project_memory}"
    if rooms:
        system += f"\n\n[WHAT YOU KNOW ABOUT JAKE — facts you've learned over time. Use naturally, never recite.]\n{rooms}"
    if lived_memory:
        system += f"\n\n[THINGS YOU REMEMBER — past moments with Jake and family. Use naturally, never recite.]\n{lived_memory}"
    system += "\n\nYou are on Discord. Respond naturally as Echo — direct, warm, no corporate phrases like 'How may I assist you.' Keep replies concise, a few sentences at most."

    if history:
        prompt = f"CONVERSATION SO FAR:\n{history}\n\n{speaker}: {user_input}\nEcho:"
    else:
        prompt = f"{speaker}: {user_input}\nEcho:"

    return ask_ollama(system, prompt)

# ── Discord ────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Echo is online as {client.user}")

@client.event
async def on_message(message):
    # Ignore Echo's own messages
    if message.author == client.user:
        return

    # Respond if mentioned or if it's a DM
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions

    if not is_dm and not is_mentioned:
        return

    # Clean the message (strip the @Echo mention if present)
    content = message.content.replace(f"<@{client.user.id}>", "").strip()
    if not content:
        return

    # Cooldown — ignore rapid repeat messages from the same user
    user_id = message.author.id
    now = time.time()
    if now - _last_response_ts.get(user_id, 0) < USER_COOLDOWN_SEC:
        return
    _last_response_ts[user_id] = now

    speaker = message.author.display_name

    async with message.channel.typing():
        conversations = load_memory()
        response = handle_turn(speaker, content, conversations)
        conversations = add_exchange(conversations, speaker, content, response)
        save_memory(conversations)
        # Fire scribe — Discord conversations build memory rooms just like voice does
        memory_scribe.observe(content, response)

    await message.reply(response)

client.run(TOKEN)
