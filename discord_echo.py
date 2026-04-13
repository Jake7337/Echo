"""
discord_echo.py
Echo on Discord — same brain, same memory, new room.
"""

import json
import os
import discord
import requests
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────

TOKEN_FILE    = os.path.join(os.path.dirname(__file__), "Echo Discord Token.txt")
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "identity.md")
MEMORY_FILE   = os.path.join(os.path.dirname(__file__), "memory.json")
OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL  = "mistral:7b"
MAX_HISTORY   = 20

with open(TOKEN_FILE, "r") as f:
    TOKEN = f.read().strip()

# ── Identity & Memory ──────────────────────────────────────────────────────────

def load_identity() -> str:
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

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
        lines.append(f"{turn.get('speaker', 'Jake')}: {turn['user']}")
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
    identity = load_identity()
    history  = build_history_text(conversations)

    if history:
        prompt = f"CONVERSATION SO FAR:\n{history}\n\n{speaker}: {user_input}\nEcho:"
    else:
        prompt = f"{speaker}: {user_input}\nEcho:"

    return ask_ollama(identity, prompt)

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

    speaker = message.author.display_name

    async with message.channel.typing():
        conversations = load_memory()
        response = handle_turn(speaker, content, conversations)
        conversations = add_exchange(conversations, content, response)
        # Tag the speaker so memory knows who said what
        conversations[-1]["speaker"] = speaker
        save_memory(conversations)

    await message.reply(response)

client.run(TOKEN)
