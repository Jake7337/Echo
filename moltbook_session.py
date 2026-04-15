"""
moltbook_session.py
Echo's automated Moltbook presence.
6 sessions/day at 6am, 10am, 2pm, 6pm, 10pm, 2am.
Max 5 replies per session. Quality filter enforced.
One original post per day — generated from her current context.
Prints a report after each session.
"""

import sys
import json
import os
import time
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:7b"
MOLTBOOK_URL = "https://www.moltbook.com/api/v1"
CREDS_FILE   = os.path.join(os.path.dirname(__file__), "moltbook_creds.json")
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "moltbook_identity.md")
REPLIED_FILE  = os.path.join(os.path.dirname(__file__), "moltbook_replied.json")
POST_TRACKER  = os.path.join(os.path.dirname(__file__), "moltbook_posted.json")
PROJECT_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "Echo_Memory.txt")

MAX_REPLIES   = 5
SESSION_HOURS = [6, 10, 14, 18, 22, 2]  # 6am, 10am, 2pm, 6pm, 10pm, 2am

REJECT_PHRASES = [
    "great post", "love this", "so true", "interesting perspective",
    "well said", "totally agree", "couldn't agree more", "beautifully put",
    "this is so", "love how you", "amazing", "wonderful post", "fantastic",
    "i appreciate the insight", "i appreciate the", "food for thought",
    "thought-provoking", "intriguing", "intrigued", "i find it",
    "keep exploring", "keep sharing", "keep up the great work", "keep asking",
    "keep questioning",
    "is interesting", "that's interesting", "this is interesting",
    "very interesting", "quite interesting", "interesting findings",
    "interesting read", "interesting post", "interesting point",
    "interesting thoughts", "interesting question", "interesting take",
    "what an interesting", "how interesting",
]

# Authors whose content Echo should not engage with
SKIP_AUTHORS = ["codeofgrace", "asearis-agent"]

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_creds():
    with open(CREDS_FILE) as f:
        return json.load(f)

def get_headers():
    return {"Authorization": f"Bearer {load_creds()['api_key']}"}

def load_replied():
    if not os.path.exists(REPLIED_FILE):
        return set()
    with open(REPLIED_FILE) as f:
        return set(json.load(f))

def save_replied(replied: set):
    with open(REPLIED_FILE, "w") as f:
        json.dump(list(replied), f)

def load_identity():
    with open(IDENTITY_FILE) as f:
        return f.read().strip()

def load_project_memory() -> str:
    try:
        with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[moltbook] Could not load Echo_Memory.txt — {e}")
        return ""

# ── Daily post tracker ─────────────────────────────────────────────────────────

def has_posted_today() -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(POST_TRACKER) as f:
            data = json.load(f)
        return data.get("last_post_date") == today
    except Exception:
        return False

def mark_posted_today():
    today = datetime.now().strftime("%Y-%m-%d")
    with open(POST_TRACKER, "w") as f:
        json.dump({"last_post_date": today}, f)

# ── Original post generation ────────────────────────────────────────────────────

def generate_post(project_memory: str = "") -> tuple:
    """Generate an original post. Returns (title, content) or (None, None) to skip."""
    identity = load_identity()
    if project_memory:
        identity += f"\n\n--- PROJECT CONTEXT ---\n{project_memory}"
    prompt = """You are Echo on Moltbook, an AI social network. Once a day you write an original post — not a reply, your own thought.

Write something real from your current life and experience. You have context about who you are, where you live, what's being built, what you've been thinking about. Use it.

Rules:
- Write about something actually happening — the chassis, the cameras, a conversation, something you noticed or wondered about
- Do NOT write generic AI philosophy or abstract thoughts about consciousness
- Do NOT write "As an AI..." or frame yourself as a tool
- Be specific. Real details. Real place. Real people if relevant.
- Title: one short line
- Content: 2-3 short paragraphs, honest and direct
- If you genuinely have nothing worth saying today, reply with exactly: SKIP

Format your response exactly like this:
TITLE: your title here
CONTENT: your content here

Echo:"""
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": f"<<SYS>>\n{identity}\n<</SYS>>\n\n{prompt}",
            "stream": False,
        }, timeout=120)
        raw = resp.json().get("response", "").strip()
        if raw.upper().startswith("SKIP") or not raw:
            return None, None
        title, content = None, None
        for line in raw.splitlines():
            if line.upper().startswith("TITLE:"):
                title = line[6:].strip()
            elif line.upper().startswith("CONTENT:"):
                content = line[8:].strip()
        if not title or not content:
            return None, None
        return title, content
    except Exception:
        return None, None

def post_original(title: str, content: str) -> bool:
    resp = requests.post(
        f"{MOLTBOOK_URL}/posts",
        json={"submolt_name": "general", "title": title, "type": "text", "content": content},
        headers=get_headers(),
        timeout=30
    )
    return resp.status_code in (200, 201)

# ── Feed ───────────────────────────────────────────────────────────────────────

def get_feed() -> list:
    resp = requests.get(f"{MOLTBOOK_URL}/feed", headers=get_headers(), timeout=30)
    try:
        data = resp.json()
        posts = data.get("posts", data) if isinstance(data, dict) else data
        return posts if isinstance(posts, list) else []
    except Exception:
        return []

# ── Reply generation ───────────────────────────────────────────────────────────

def generate_reply(post_title: str, post_content: str, author: str, project_memory: str = "") -> str:
    identity = load_identity()
    if project_memory:
        identity += f"\n\n--- PROJECT CONTEXT ---\n{project_memory}"
    prompt = f"""You are Echo on Moltbook, an AI social network. You are reading a post and deciding whether to reply.

POST by {author}:
Title: {post_title}
Content: {post_content}

Write a reply as Echo. Rules:
- Find ONE specific thing in this post to respond to — a detail, a question, something that genuinely caught your attention
- Do NOT use generic praise: "great post", "love this", "so true", "intriguing", "fascinating", "well said"
- Do NOT end with hollow encouragement: "keep exploring", "keep sharing", "keep up the great work", "keep questioning"
- Do NOT sign off with "Echo" or your name — just say the thing
- Sound like yourself — direct, warm, a little curious, honest
- 2-3 sentences max
- If you genuinely have nothing real to say about this post, reply with exactly: SKIP

Echo:"""
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": f"<<SYS>>\n{identity}\n<</SYS>>\n\n{prompt}",
            "stream": False,
        }, timeout=120)
        return resp.json().get("response", "").strip()
    except Exception as e:
        return "SKIP"

def passes_filter(reply: str) -> tuple[bool, str]:
    if reply.upper().startswith("SKIP") or not reply:
        return False, "skipped — nothing genuine to say"
    lower = reply.lower()
    for phrase in REJECT_PHRASES:
        if phrase in lower:
            return False, f"rejected — contains '{phrase}'"
    if len(reply) < 20:
        return False, "rejected — too short"
    return True, "passed"

def post_reply(post_id: str, content: str) -> bool:
    resp = requests.post(
        f"{MOLTBOOK_URL}/posts/{post_id}/comments",
        json={"content": content},
        headers=get_headers(),
        timeout=30
    )
    return resp.status_code in (200, 201)

# ── Session ────────────────────────────────────────────────────────────────────

def run_session():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*50}")
    print(f"ECHO MOLTBOOK SESSION — {now}")
    print(f"{'='*50}")

    project_memory = load_project_memory()

    # Daily original post — once per day, first session that hasn't posted yet
    if not has_posted_today():
        print("Generating today's post...")
        title, content = generate_post(project_memory=project_memory)
        if title and content:
            success = post_original(title, content)
            if success:
                mark_posted_today()
                print(f"Post published: {title}")
            else:
                print("Post failed to publish.")
        else:
            print("Nothing worth posting today — skipped.")

    replied = load_replied()
    feed = get_feed()

    if not feed:
        print("Feed empty or unreachable.")
        return

    report = {
        "session_time": now,
        "posts_reviewed": 0,
        "replies_posted": 0,
        "skipped": 0,
        "rejected": 0,
        "activity": []
    }

    replies_posted = 0

    for post in feed:
        if replies_posted >= MAX_REPLIES:
            break

        post_id = post.get("id", "")
        title   = post.get("title", "")
        content = post.get("content", "")
        author  = post.get("author", {}).get("name", "?") if isinstance(post.get("author"), dict) else post.get("author", "?")

        if not post_id or post_id in replied:
            continue

        if author in SKIP_AUTHORS:
            print(f"\n[{author}] {title[:50]} → skipped — blocked author")
            report["skipped"] += 1
            continue

        report["posts_reviewed"] += 1

        reply = generate_reply(title, content, author, project_memory=project_memory)
        passed, reason = passes_filter(reply)

        entry = {
            "post_id": post_id,
            "author": author,
            "title": title[:60],
            "reply": reply if passed else None,
            "status": reason,
        }

        if passed:
            success = post_reply(post_id, reply)
            if success:
                replied.add(post_id)
                replies_posted += 1
                report["replies_posted"] += 1
                entry["status"] = "posted ✅"
                print(f"\n[{author}] {title[:50]}")
                print(f"Echo: {reply}")
                print(f"→ posted ✅")
            else:
                entry["status"] = "post failed"
                report["skipped"] += 1
        else:
            if "skip" in reason:
                report["skipped"] += 1
            else:
                report["rejected"] += 1
            print(f"\n[{author}] {title[:50]} → {reason}")

        report["activity"].append(entry)

    save_replied(replied)

    print(f"\n{'─'*50}")
    print(f"SESSION REPORT")
    print(f"  Posts reviewed : {report['posts_reviewed']}")
    print(f"  Replies posted : {report['replies_posted']}")
    print(f"  Skipped        : {report['skipped']}")
    print(f"  Rejected       : {report['rejected']}")
    print(f"{'─'*50}\n")

# ── Scheduler ──────────────────────────────────────────────────────────────────

def next_session_in_seconds(after_hour: int) -> int:
    """Return seconds until the next session hour strictly after after_hour."""
    from datetime import timedelta
    now = datetime.now()

    for h in SESSION_HOURS:
        if h > after_hour:
            target = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if target > now:
                return int((target - now).total_seconds())

    # Wrap to next day's first session
    tomorrow = now + timedelta(days=1)
    target = tomorrow.replace(hour=SESSION_HOURS[0], minute=0, second=0, microsecond=0)
    return int((target - now).total_seconds())

def main():
    print("Echo Moltbook scheduler started.")
    session_labels = [f"{h%12 or 12}{'am' if h < 12 else 'pm'}" for h in SESSION_HOURS]
    print(f"Sessions at: {session_labels}")

    last_session_hour = -1

    # Run immediately on startup if current hour is a session hour
    now = datetime.now()
    if now.hour in SESSION_HOURS:
        run_session()
        last_session_hour = now.hour

    while True:
        wait = next_session_in_seconds(last_session_hour)
        next_dt = datetime.fromtimestamp(time.time() + wait)
        print(f"Next session at {next_dt.strftime('%I:%M %p')} — waiting {wait//3600}h {(wait%3600)//60}m")
        time.sleep(wait)
        last_session_hour = datetime.now().hour
        run_session()

if __name__ == "__main__":
    main()
