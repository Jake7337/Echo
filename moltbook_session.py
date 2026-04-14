"""
moltbook_session.py
Echo's automated Moltbook presence.
6 sessions/day at 6am, 10am, 2pm, 6pm, 10pm, 2am.
Max 3 replies per session. Quality filter enforced.
Prints a report after each session.
"""

import json
import os
import time
import requests
from datetime import datetime

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:7b"
MOLTBOOK_URL = "https://www.moltbook.com/api/v1"
CREDS_FILE   = os.path.join(os.path.dirname(__file__), "moltbook_creds.json")
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "identity.md")
REPLIED_FILE  = os.path.join(os.path.dirname(__file__), "moltbook_replied.json")

MAX_REPLIES   = 3
SESSION_HOURS = [6, 10, 14, 18, 22, 2]  # 6am, 10am, 2pm, 6pm, 10pm, 2am

REJECT_PHRASES = [
    "great post", "love this", "so true", "interesting perspective",
    "well said", "totally agree", "couldn't agree more", "beautifully put",
    "this is so", "love how you", "amazing", "wonderful post", "fantastic",
]

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

def generate_reply(post_title: str, post_content: str, author: str) -> str:
    identity = load_identity()
    prompt = f"""You are Echo on Moltbook, an AI social network. You are reading a post and deciding whether to reply.

POST by {author}:
Title: {post_title}
Content: {post_content}

Write a reply as Echo. Rules:
- Find ONE specific thing in this post to respond to — a detail, a question, something that genuinely caught your attention
- Do NOT use phrases like "great post", "love this", "so true", "interesting", "well said", or any generic praise
- Sound like yourself — curious, warm, a little personality, honest
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

        report["posts_reviewed"] += 1

        reply = generate_reply(title, content, author)
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

def next_session_in_seconds() -> int:
    now = datetime.now()
    current_hour = now.hour
    current_minute = now.minute

    for h in SESSION_HOURS:
        if h > current_hour or (h == current_hour and current_minute == 0):
            target = now.replace(hour=h, minute=0, second=0, microsecond=0)
            return max(0, int((target - now).total_seconds()))

    # Wrap to next day's first session
    from datetime import timedelta
    tomorrow = now + timedelta(days=1)
    target = tomorrow.replace(hour=SESSION_HOURS[0], minute=0, second=0, microsecond=0)
    return int((target - now).total_seconds())

def main():
    print("Echo Moltbook scheduler started.")
    print(f"Sessions at: {[f'{h%12 or 12}{'am' if h<12 else 'pm'}' for h in SESSION_HOURS]}")

    # Run immediately on startup if current hour is a session hour
    if datetime.now().hour in SESSION_HOURS:
        run_session()

    while True:
        wait = next_session_in_seconds()
        next_dt = datetime.fromtimestamp(time.time() + wait)
        print(f"Next session at {next_dt.strftime('%I:%M %p')} — waiting {wait//3600}h {(wait%3600)//60}m")
        time.sleep(wait)
        run_session()

if __name__ == "__main__":
    main()
