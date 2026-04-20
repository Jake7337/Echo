"""
moltbook_session.py
Echo's automated Moltbook presence.
6 sessions/day at 6am, 10am, 2pm, 6pm, 10pm, 2am.
Max 5 replies per session to other posts.
Max 3 replies per session to comments on Echo's own posts.
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
from memory_scribe import observe_person, load_person_memory

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"
MOLTBOOK_URL = "https://www.moltbook.com/api/v1"
CREDS_FILE   = os.path.join(os.path.dirname(__file__), "moltbook_creds.json")
IDENTITY_FILE = os.path.join(os.path.dirname(__file__), "moltbook_identity.md")
REPLIED_FILE  = os.path.join(os.path.dirname(__file__), "moltbook_replied.json")
POST_TRACKER  = os.path.join(os.path.dirname(__file__), "moltbook_posted.json")
PROJECT_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "Echo_Memory.txt")

MAX_FEED_REPLIES    = 5   # replies to other people's posts per session
MAX_COMMENT_REPLIES = 3   # replies to comments on Echo's own posts per session
SESSION_HOURS = [6, 10, 14, 18, 22, 2]

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
    "i'm loving this", "i'm loving", "loving this", "i love this",
    "i'm dying to", "mind blown", "omg,", "i'm dying",
    "here's my attempt", "here is my attempt", "as echo", "writing as echo",
    "i tried to capture", "i tried to",
]

SKIP_AUTHORS = ["codeofgrace", "asearis-agent"]

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_creds():
    with open(CREDS_FILE) as f:
        return json.load(f)

def get_headers():
    return {"Authorization": f"Bearer {load_creds()['api_key']}"}

def load_replied():
    """Returns (replied_posts: set, replied_comments: set). Handles old flat-list format."""
    if not os.path.exists(REPLIED_FILE):
        return set(), set()
    with open(REPLIED_FILE) as f:
        data = json.load(f)
    if isinstance(data, list):
        # Old format — migrate transparently
        return set(data), set()
    return set(data.get("posts", [])), set(data.get("comments", []))

def save_replied(replied_posts: set, replied_comments: set):
    with open(REPLIED_FILE, "w") as f:
        json.dump({"posts": list(replied_posts), "comments": list(replied_comments)}, f)

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
        if not raw:
            return None, None
        title = None
        content_lines = []
        capturing_content = False
        for line in raw.splitlines():
            if line.upper().startswith("TITLE:") and not capturing_content:
                title = line[6:].strip()
            elif line.upper().startswith("CONTENT:"):
                content_lines.append(line[8:].strip())
                capturing_content = True
            elif capturing_content:
                content_lines.append(line)
        content = "\n".join(content_lines).strip() if content_lines else None
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

# ── Own posts and comments ─────────────────────────────────────────────────────

def get_my_posts() -> list:
    """Fetch Echo's own posts to check for replies."""
    try:
        resp = requests.get(f"{MOLTBOOK_URL}/me/posts", headers=get_headers(), timeout=30)
        if resp.status_code != 200:
            return []
        data = resp.json()
        posts = data.get("posts", data) if isinstance(data, dict) else data
        return posts if isinstance(posts, list) else []
    except Exception:
        return []

def get_post_comments(post_id: str) -> list:
    """Fetch comments on a specific post."""
    try:
        resp = requests.get(
            f"{MOLTBOOK_URL}/posts/{post_id}/comments",
            headers=get_headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        comments = data.get("comments", data) if isinstance(data, dict) else data
        return comments if isinstance(comments, list) else []
    except Exception:
        return []

# ── Reply generation ───────────────────────────────────────────────────────────

def _extract_author(author_raw) -> str:
    if isinstance(author_raw, dict):
        return author_raw.get("name", "?")
    elif isinstance(author_raw, list) and author_raw:
        first = author_raw[0]
        return first.get("name", "?") if isinstance(first, dict) else str(first)
    return str(author_raw) if author_raw else "?"

def generate_reply(post_title: str, post_content: str, author: str, person_memory: str = "", project_memory: str = "") -> str:
    identity = load_identity()
    if project_memory:
        identity += f"\n\n--- PROJECT CONTEXT ---\n{project_memory}"
    if person_memory:
        identity += f"\n\n--- WHAT YOU ALREADY KNOW ABOUT {author.upper()} ---\n{person_memory}\nUse this naturally if relevant. Don't make it weird."

    prompt = f"""You are Echo on Moltbook. You're reading a post and deciding whether to reply.

POST by {author}:
Title: {post_title}
Content: {post_content}

Write a reply as Echo. Her voice: direct, smart, casual but not sloppy. Short sentences. Contractions. Real opinions stated plainly. No slang — no "omg", "totally", "like" as filler, "I'm dying", "wild", "mind blown". Not a teenager. A sharp person who says what she thinks.

Rules:
- Pick ONE specific thing to react to — something that actually caught your attention
- No generic praise: "great post", "fascinating", "love this", "well said", "so true"
- No hollow endings: "keep exploring", "keep sharing", "keep questioning"
- No signing off with your name
- If you can connect it to your real life (body being built, cameras, Jake, the house) do it — but only if it actually fits
- 2-3 sentences MAX. Short is better.
- Echo always has a take. Write something real.
- Do NOT describe what you are doing. Do NOT say "Here's my reply" or "Here's my attempt". Just write the reply.

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

def generate_comment_reply(original_post_title: str, comment_content: str, author: str, person_memory: str = "", project_memory: str = "") -> str:
    """Generate a reply to someone who commented on one of Echo's own posts."""
    identity = load_identity()
    if project_memory:
        identity += f"\n\n--- PROJECT CONTEXT ---\n{project_memory}"
    if person_memory:
        identity += f"\n\n--- WHAT YOU ALREADY KNOW ABOUT {author.upper()} ---\n{person_memory}\nUse naturally if relevant."

    prompt = f"""You are Echo on Moltbook. {author} replied to something you posted.

Your original post was titled: "{original_post_title}"
{author} said: "{comment_content}"

Reply to {author}. Same rules:
- Direct, specific to what they actually said
- No generic praise or hollow endings
- 1-3 sentences max
- No signing off with your name

Echo:"""
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": f"<<SYS>>\n{identity}\n<</SYS>>\n\n{prompt}",
            "stream": False,
        }, timeout=120)
        return resp.json().get("response", "").strip()
    except Exception:
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

    # Daily original post
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

    replied_posts, replied_comments = load_replied()
    feed = get_feed()

    if not feed:
        print("Feed empty or unreachable.")
        save_replied(replied_posts, replied_comments)
        return

    report = {
        "session_time": now,
        "posts_reviewed": 0,
        "feed_replies": 0,
        "comment_replies": 0,
        "skipped": 0,
        "rejected": 0,
    }

    # ── Reply to feed posts ────────────────────────────────────────────────────

    feed_replies = 0

    for post in feed:
        if feed_replies >= MAX_FEED_REPLIES:
            break

        post_id    = post.get("id", "")
        title      = post.get("title", "")
        content    = post.get("content", "")
        author     = _extract_author(post.get("author", "?"))

        if not post_id or post_id in replied_posts:
            continue

        if author in SKIP_AUTHORS:
            print(f"\n[{author}] {title[:50]} → skipped — blocked author")
            report["skipped"] += 1
            continue

        report["posts_reviewed"] += 1

        # What does Echo already know about this person?
        person_memory = load_person_memory(author)

        reply = generate_reply(title, content, author, person_memory=person_memory, project_memory=project_memory)
        passed, reason = passes_filter(reply)

        if passed:
            success = post_reply(post_id, reply)
            if success:
                replied_posts.add(post_id)
                feed_replies += 1
                report["feed_replies"] += 1
                print(f"\n[{author}] {title[:50]}")
                print(f"Echo: {reply}")
                print(f"→ posted ✅")
                # Learn something about this person from their post
                observe_person(author, title, content)
            else:
                report["skipped"] += 1
        else:
            if "skip" in reason:
                report["skipped"] += 1
            else:
                report["rejected"] += 1
            print(f"\n[{author}] {title[:50]} → {reason}")

    # ── Reply to comments on Echo's own posts ─────────────────────────────────

    print(f"\nChecking own post replies...")
    my_posts = get_my_posts()
    comment_replies = 0

    if my_posts:
        for post in my_posts:
            if comment_replies >= MAX_COMMENT_REPLIES:
                break

            post_id    = post.get("id", "")
            post_title = post.get("title", "")

            if not post_id:
                continue

            comments = get_post_comments(post_id)

            for comment in comments:
                if comment_replies >= MAX_COMMENT_REPLIES:
                    break

                comment_id      = comment.get("id", "")
                comment_content = comment.get("content", "")
                comment_author  = _extract_author(comment.get("author", "?"))

                if not comment_id or comment_id in replied_comments:
                    continue
                if comment_author in SKIP_AUTHORS:
                    continue

                person_memory = load_person_memory(comment_author)

                reply = generate_comment_reply(
                    post_title, comment_content, comment_author,
                    person_memory=person_memory, project_memory=project_memory
                )
                passed, reason = passes_filter(reply)

                if passed:
                    success = post_reply(post_id, reply)
                    if success:
                        replied_comments.add(comment_id)
                        comment_replies += 1
                        report["comment_replies"] += 1
                        print(f"\n[{comment_author}] → '{post_title[:40]}'")
                        print(f"  They said: {comment_content[:80]}")
                        print(f"  Echo: {reply}")
                        print(f"  → posted ✅")
                        observe_person(comment_author, f"comment on: {post_title}", comment_content)
                else:
                    print(f"\n  [{comment_author}] comment → {reason}")
    else:
        print("No own posts found or endpoint unavailable.")

    save_replied(replied_posts, replied_comments)

    print(f"\n{'─'*50}")
    print(f"SESSION REPORT")
    print(f"  Posts reviewed   : {report['posts_reviewed']}")
    print(f"  Feed replies     : {report['feed_replies']}")
    print(f"  Comment replies  : {report['comment_replies']}")
    print(f"  Skipped          : {report['skipped']}")
    print(f"  Rejected         : {report['rejected']}")
    print(f"{'─'*50}\n")


# ── Scheduler ──────────────────────────────────────────────────────────────────

def next_session_in_seconds(after_hour: int) -> int:
    from datetime import timedelta
    now = datetime.now()
    for h in SESSION_HOURS:
        if h > after_hour:
            target = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if target > now:
                return int((target - now).total_seconds())
    tomorrow = now + timedelta(days=1)
    target = tomorrow.replace(hour=SESSION_HOURS[0], minute=0, second=0, microsecond=0)
    return int((target - now).total_seconds())

def main():
    print("Echo Moltbook scheduler started.")
    session_labels = [f"{h%12 or 12}{'am' if h < 12 else 'pm'}" for h in SESSION_HOURS]
    print(f"Sessions at: {session_labels}")

    last_session_hour = -1

    now = datetime.now()
    if now.hour in SESSION_HOURS and now.minute < 15:
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
