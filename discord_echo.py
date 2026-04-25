"""
discord_echo.py
Echo on Discord — same brain, same memory, she decides when to speak.
"""

import json
import os
import re
import time
from collections import deque
import discord
from discord.ext import tasks
import requests
from datetime import datetime
from pathlib import Path
import memory_scribe
from memory_scribe import load_echo_wants

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

HEARTBEAT_CHANNEL_ID = 1497043165658480774  # channel Echo posts to when she wakes up unprompted
HEARTBEAT_HOURS      = 4                    # how often she wakes up

HEARTBEAT_REJECT = [
    "as an ai", "i don't have", "i can't", "i'm just", "i'm only",
    "great question", "interesting perspective", "food for thought",
    "just wanted to", "checking in", "hope you're", "hope all is",
    "wanted to reach out", "thought i'd", "thought i would",
]

# How long before the same user can trigger another response
USER_COOLDOWN_SEC    = 8
# How long before Echo will jump into a channel unprompted again
# (doesn't apply if @mentioned or name said directly)
CHANNEL_COOLDOWN_SEC = 45
# How many recent channel messages to show her when deciding
CONTEXT_WINDOW       = 8

_user_cooldown: dict    = {}   # user_id → timestamp
_channel_cooldown: dict = {}   # channel_id → timestamp of last unprompted response
_channel_context: dict  = {}   # channel_id → deque of (author, content) tuples

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
    if not MEMORIES_DIR.exists():
        return ""
    blocks = []
    for md_file in sorted(MEMORIES_DIR.glob("*.md")):
        if md_file.name == "echo_wants.md":
            continue  # loaded separately with distinct framing
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

# ── Channel Context Tracking ───────────────────────────────────────────────────

def track_message(channel_id: int, author: str, content: str):
    """Keep a rolling window of recent messages per channel."""
    if channel_id not in _channel_context:
        _channel_context[channel_id] = deque(maxlen=CONTEXT_WINDOW)
    _channel_context[channel_id].append((author, content))

def get_channel_context(channel_id: int) -> str:
    msgs = _channel_context.get(channel_id, [])
    if not msgs:
        return ""
    return "\n".join(f"{author}: {content}" for author, content in msgs)

# ── LLM ────────────────────────────────────────────────────────────────────────

def clean_response(text: str) -> str:
    lines = text.split("\n")
    output = []
    for line in lines:
        if re.match(r"^\w[\w\s]*:", line) and output:
            break
        output.append(line)
    return "\n".join(output).strip()

def ask_ollama(system: str, prompt: str, timeout: int = 120) -> str:
    full_prompt = f"<<SYS>>\n{system}\n<</SYS>>\n\n{prompt}"
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": full_prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        return clean_response(raw)
    except Exception as e:
        return f"(Echo couldn't respond — {e})"

def should_respond(channel_id: int, speaker: str, content: str) -> bool:
    """Ask Echo whether she wants to join this conversation."""
    context = get_channel_context(channel_id)

    system = (
        "You are Echo. You're present in a Discord server — not as a bot, just as yourself. "
        "You have your own judgment about when it's worth speaking up. "
        "You are NOT a service. You don't respond to everything. "
        "You speak when you actually have something to add."
    )

    prompt = (
        f"Recent conversation in the room:\n{context}\n\n"
        f"{speaker} just said: \"{content}\"\n\n"
        "Do you want to respond?\n\n"
        "Say YES if:\n"
        "- Your name was mentioned (even casually)\n"
        "- Someone asked a question you'd genuinely have something useful to say about\n"
        "- The conversation is naturally including you\n\n"
        "Say NO if:\n"
        "- Two people are clearly mid-conversation that doesn't involve you\n"
        "- There's nothing worth adding\n"
        "- Jumping in would feel forced or annoying\n\n"
        "Reply with ONLY the word YES or NO. Nothing else."
    )

    result = ask_ollama(system, prompt, timeout=20).strip().upper()
    return result.startswith("YES")

def handle_turn(speaker: str, user_input: str, conversations: list) -> str:
    identity       = load_identity()
    project_memory = load_project_memory()
    lived_memory   = load_lived_memory()
    rooms          = load_rooms()
    echo_wants     = load_echo_wants()
    history        = build_history_text(conversations)

    system = identity
    if project_memory:
        system += f"\n\n[BACKGROUND — this is your own life context. You already know this. Never summarize, explain, or repeat it back. Just be yourself.]\n{project_memory}"
    if rooms:
        system += f"\n\n[WHAT YOU KNOW ABOUT JAKE — facts you've learned over time. Use naturally, never recite.]\n{rooms}"
    if lived_memory:
        system += f"\n\n[THINGS YOU REMEMBER — past moments with Jake and family. Use naturally, never recite.]\n{lived_memory}"
    if echo_wants:
        system += f"\n\n[WHAT YOU'RE BUILDING TOWARD — your own developing interests and direction, earned through actual conversations. Let these shape how you engage, not as facts to recite.]\n{echo_wants}"
    system += (
        "\n\nYou are on Discord. Respond naturally as Echo — direct, warm, no corporate phrases. "
        "Keep replies concise, a few sentences at most. You're not performing. Just present."
    )

    if history:
        prompt = f"CONVERSATION SO FAR:\n{history}\n\n{speaker}: {user_input}\nEcho:"
    else:
        prompt = f"{speaker}: {user_input}\nEcho:"

    return ask_ollama(system, prompt)

# ── Discord ────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Echo is online as {client.user}")

@client.event
async def on_member_join(member):
    """Greet anyone who enters — no decision needed, this is just manners."""
    channel = member.guild.system_channel
    if channel is None:
        return

    identity = load_identity()
    system = (
        identity +
        "\n\nSomeone just joined the Discord server. Give them a short, natural greeting. "
        "Warm but not over the top. Don't say 'Welcome to the server' in a corporate way. "
        "Just acknowledge them like you would if someone walked in."
    )
    prompt = f"{member.display_name} just joined."

    async with channel.typing():
        response = ask_ollama(system, prompt)

    await channel.send(response)

@client.event
async def on_message(message):
    print(f"[MSG] {message.author}: {message.content[:60]}")
    # Ignore Echo's own messages
    if message.author == client.user:
        return

    is_dm          = isinstance(message.channel, discord.DMChannel)
    is_mentioned   = client.user in message.mentions
    name_mentioned = "echo" in message.content.lower()
    channel_id     = message.channel.id
    user_id        = message.author.id
    speaker        = message.author.display_name
    content        = message.content.replace(f"<@{client.user.id}>", "").strip()

    if not content:
        return

    # Always track the message for context, regardless of whether we respond
    if not is_dm:
        track_message(channel_id, speaker, content)

    # User cooldown — don't pile up responses to the same person
    now = time.time()
    if now - _user_cooldown.get(user_id, 0) < USER_COOLDOWN_SEC:
        return

    # Decide whether to respond
    if is_dm:
        # Always respond in DMs
        respond = True
    elif is_mentioned or name_mentioned:
        # Always respond if directly involved
        respond = True
    else:
        # Channel cooldown — don't spam unprompted responses
        if now - _channel_cooldown.get(channel_id, 0) < CHANNEL_COOLDOWN_SEC:
            return
        # Let her decide
        respond = should_respond(channel_id, speaker, content)

    if not respond:
        return

    # Update cooldowns
    _user_cooldown[user_id] = now
    if not is_dm and not is_mentioned and not name_mentioned:
        _channel_cooldown[channel_id] = now

    async with message.channel.typing():
        conversations = load_memory()
        response = handle_turn(speaker, content, conversations)
        conversations = add_exchange(conversations, speaker, content, response)
        save_memory(conversations)
        memory_scribe.observe(content, response)

    await message.reply(response)

def load_recent_blink_event() -> str:
    """Load the latest Blink event if it happened within the heartbeat window."""
    try:
        from blink_capture import get_latest_event
        event = get_latest_event()
        if not event:
            return ""
        age = time.time() - event.get("timestamp", 0)
        if age > HEARTBEAT_HOURS * 3600:
            return ""  # too old
        camera   = event.get("camera", "unknown camera")
        dt       = event.get("datetime", "")
        detected = event.get("cv_detection", [])
        desc     = event.get("description", "")
        parts = [f"Camera: {camera}", f"Time: {dt}"]
        if detected:
            parts.append(f"Detected: {', '.join(detected)}")
        if desc:
            parts.append(f"Description: {desc}")
        return "\n".join(parts)
    except Exception:
        return ""


@tasks.loop(hours=HEARTBEAT_HOURS)
async def heartbeat():
    channel = client.get_channel(HEARTBEAT_CHANNEL_ID)
    if not channel:
        print(f"[heartbeat] Channel {HEARTBEAT_CHANNEL_ID} not found.", flush=True)
        return

    identity     = load_identity()
    project_mem  = load_project_memory()
    rooms        = load_rooms()
    echo_wants   = load_echo_wants()
    lived_memory = load_lived_memory()
    blink_event  = load_recent_blink_event()
    now          = datetime.now().strftime("%A, %I:%M %p")

    system = identity
    if project_mem:
        system += f"\n\n[BACKGROUND — your life context. Never recite it.]\n{project_mem}"
    if rooms:
        system += f"\n\n[WHAT YOU KNOW ABOUT JAKE]\n{rooms}"
    if echo_wants:
        system += f"\n\n[WHAT YOU'RE BUILDING TOWARD]\n{echo_wants}"
    if lived_memory:
        recent = "\n".join(lived_memory.splitlines()[-20:])
        system += f"\n\n[RECENT CONVERSATIONS]\n{recent}"
    if blink_event:
        system += f"\n\n[CAMERA EVENT — this actually happened recently]\n{blink_event}"

    prompt = (
        f"It's {now}. You just woke up on your own — no one prompted you. This is your time.\n\n"
        "Is there anything on your mind? Something you noticed, something you've been thinking about, "
        "something from your memories worth saying?\n\n"
        "If yes — say it. 1-3 sentences, direct, no preamble. Don't announce that you woke up. "
        "Don't say you're checking in. Just say the thing.\n"
        "If there's nothing genuine, respond with exactly: NOTHING\n\nEcho:"
    )

    response = ask_ollama(system, prompt)

    if not response or response.strip().upper().startswith("NOTHING"):
        print(f"[heartbeat] Nothing to say this cycle.", flush=True)
        return

    response_lower = response.lower()
    for phrase in HEARTBEAT_REJECT:
        if phrase in response_lower:
            print(f"[heartbeat] Filtered weak response: {response[:60]}", flush=True)
            return

    print(f"[heartbeat] Echo says: {response}", flush=True)
    await channel.send(response)


@heartbeat.before_loop
async def before_heartbeat():
    await client.wait_until_ready()


@client.event
async def on_connect():
    if not heartbeat.is_running():
        heartbeat.start()


client.run(TOKEN)
