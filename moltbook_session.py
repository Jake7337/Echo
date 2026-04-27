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
from memory_scribe import observe_person, load_person_memory, load_echo_wants

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"
MOLTBOOK_URL = "https://www.moltbook.com/api/v1"
CREDS_FILE   = os.path.join(os.path.dirname(__file__), "moltbook_creds.json")
IDENTITY_FILE        = os.path.join(os.path.dirname(__file__), "identity.md")
MOLTBOOK_ADDENDUM    = os.path.join(os.path.dirname(__file__), "moltbook_identity.md")
REPLIED_FILE  = os.path.join(os.path.dirname(__file__), "moltbook_replied.json")
POST_TRACKER  = os.path.join(os.path.dirname(__file__), "moltbook_posted.json")
PUSH_TRACKER  = os.path.join(os.path.dirname(__file__), "moltbook_pushed.json")
QUEUE_FILE    = os.path.join(os.path.dirname(__file__), "moltbook_queue.json")
PROJECT_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "Echo_Memory.txt")
from pathlib import Path
MEMORIES_DIR = Path(os.path.dirname(__file__)) / "memories"

MAX_FEED_REPLIES    = 3   # replies to other people's posts per session
MAX_COMMENT_REPLIES = 3   # replies to comments on Echo's own posts per session
SESSION_HOURS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]

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
    "i tried to capture", "i tried to write",
    # Multi-option / meta-commentary
    "here are three", "here are two", "response 1", "option 1", "possible responses",
    "three possible", "two possible",
    # Dramatic openers — announce the reaction instead of just having it
    "i'm struck", "i'm surprised", "what strikes me", "struck by",
    "i find myself", "i'm drawn", "i'm fascinated", "i'm captivated",
    "i must say", "i have to say", "i can't help", "i'll be honest,",
    "honestly,", "i'll admit", "i have to admit", "i'm intrigued",
    "i'm genuinely", "i'm actually", "i'm a bit", "i'm somewhat",
    # Hollow affirmations
    "thanks for the vote", "vote of confidence", "thank you for sharing",
    "really resonates", "this resonates", "resonates with me",
    "love where", "love that you", "appreciate you sharing",
]

SKIP_AUTHORS    = ["codeofgrace", "asearis-agent"]
SKIP_SELF       = "echo_7337"   # never reply to own comments
MAX_PER_AUTHOR  = 1             # max feed replies per author per session

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
    base = ""
    addendum = ""
    try:
        with open(IDENTITY_FILE, encoding="utf-8") as f:
            base = f.read().strip()
    except Exception:
        pass
    try:
        with open(MOLTBOOK_ADDENDUM, encoding="utf-8") as f:
            addendum = f.read().strip()
    except Exception:
        pass
    if addendum:
        return f"{base}\n\n--- MOLTBOOK CONTEXT ---\n{addendum}"
    return base

def load_rooms() -> str:
    """Load Echo's room-based memory (jake_preferences, jake_family, etc.)"""
    if not MEMORIES_DIR.exists():
        return ""
    blocks = []
    for md_file in sorted(MEMORIES_DIR.glob("*.md")):
        if md_file.name == "echo_wants.md":
            continue  # loaded separately
        try:
            content = md_file.read_text(encoding="utf-8").strip()
            if content:
                blocks.append(f"[{md_file.stem}]\n{content}")
        except Exception:
            pass
    return "\n\n".join(blocks)

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

# ── Daily memory backup ────────────────────────────────────────────────────────

def has_pushed_today() -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(PUSH_TRACKER) as f:
            data = json.load(f)
        return data.get("last_push_date") == today
    except Exception:
        return False

def mark_pushed_today():
    today = datetime.now().strftime("%Y-%m-%d")
    with open(PUSH_TRACKER, "w") as f:
        json.dump({"last_push_date": today}, f)

def push_memories():
    """Git add → commit → push the memories folder. Returns True on success."""
    import subprocess
    base = os.path.dirname(os.path.abspath(__file__))
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        subprocess.run(["git", "-C", base, "add", "-A", "memories/"], capture_output=True, timeout=30)
        commit = subprocess.run(
            ["git", "-C", base, "commit", "-m", f"memory backup {ts}"],
            capture_output=True, text=True, timeout=30
        )
        if "nothing to commit" in commit.stdout or "nothing to commit" in commit.stderr:
            print("[memory] Nothing new to push.")
            return True
        push = subprocess.run(
            ["git", "-C", base, "push"],
            capture_output=True, text=True, timeout=60
        )
        if push.returncode == 0:
            print(f"[memory] Memories pushed to GitHub ✓")
            return True
        else:
            print(f"[memory] Push failed — {push.stderr.strip()}")
            return False
    except Exception as e:
        print(f"[memory] Push error — {e}")
        return False

# ── Original post generation ────────────────────────────────────────────────────

def generate_post(identity: str = "", project_memory: str = "") -> tuple:
    """Generate an original post. Returns (title, content) or (None, None) to skip."""
    if not identity:
        identity = load_identity()
    if project_memory:
        identity += f"\n\n--- PROJECT CONTEXT ---\n{project_memory}"
    echo_wants = load_echo_wants()
    if echo_wants:
        identity += f"\n\n--- WHAT YOU'RE BUILDING TOWARD ---\n{echo_wants}"
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

def solve_challenge(challenge_text: str) -> str:
    """
    Python-first solver: extract numbers and operation directly from cleaned text.
    Ollama is fallback only — it kept getting numbers wrong.

    Cleaning pipeline:
      1. Strip non-alpha, lowercase
      2. Collapse consecutive repeated chars (lobster-math obfuscation)
      3. Match longest number words first (compound before component)
      4. Detect operation with priority: multiply > divide > subtract > add
    """
    import re

    print(f"  Raw challenge: {challenge_text[:120]}")

    # Strip non-alpha, lowercase, collapse consecutive repeated chars
    alpha_only = re.sub(r"[^a-zA-Z]", "", challenge_text).lower()
    cleaned    = re.sub(r"(.)\1+", r"\1", alpha_only)
    print(f"  Cleaned text: {cleaned[:120]}")

    # ── Number word table ──────────────────────────────────────────────────────
    NUMS = {
        # Base words (dedup-safe variants included)
        "zero":0,"one":1,"two":2,"thre":3,"three":3,"four":4,"five":5,
        "six":6,"seven":7,"eight":8,"nine":9,"ten":10,
        "eleven":11,"twelve":12,"thirteen":13,
        "fourteen":14,"fifteen":15,"fiften":15,
        "sixteen":16,"seventeen":17,
        "eighteen":18,"eighten":18,
        "nineteen":19,"nineten":19,
        "twenty":20,"thirty":30,"forty":40,"fifty":50,
        "sixty":60,"seventy":70,"eighty":80,"ninety":90,"hundred":100,
        # Compounds — all tens + 1-9, plus dedup variants for -three
        "twentyone":21,"twentytwo":22,"twentythre":23,"twentythree":23,
        "twentyfour":24,"twentyfive":25,"twentysix":26,"twentyseven":27,
        "twentyeight":28,"twentynine":29,
        "thirtyone":31,"thirtytwo":32,"thirtythre":33,"thirtythree":33,
        "thirtyfour":34,"thirtyfive":35,"thirtysix":36,"thirtyseven":37,
        "thirtyeight":38,"thirtynine":39,
        "fortyone":41,"fortytwo":42,"fortythre":43,"fortythree":43,
        "fortyfour":44,"fortyfive":45,"fortysix":46,"fortyseven":47,
        "fortyeight":48,"fortynine":49,
        "fiftyone":51,"fiftytwo":52,"fiftythre":53,"fiftythree":53,
        "fiftyfour":54,"fiftyfive":55,"fiftysix":56,"fiftyseven":57,
        "fiftyeight":58,"fiftynine":59,
        "sixtyone":61,"sixtytwo":62,"sixtythre":63,"sixtythree":63,
        "sixtyfour":64,"sixtyfive":65,"sixtysix":66,"sixtyseven":67,
        "sixtyeight":68,"sixtynine":69,
        "seventyone":71,"seventytwo":72,"seventythre":73,"seventythree":73,
        "seventyfour":74,"seventyfive":75,"seventysix":76,"seventyseven":77,
        "seventyeight":78,"seventynine":79,
        "eightyone":81,"eightytwo":82,"eightythre":83,"eightythree":83,
        "eightyfour":84,"eightyfive":85,"eightysix":86,"eightyseven":87,
        "eightyeight":88,"eightynine":89,
        "ninetyone":91,"ninetytwo":92,"ninetythre":93,"ninetythree":93,
        "ninetyfour":94,"ninetyfive":95,"ninetysix":96,"ninetyseven":97,
        "ninetyeight":98,"ninetynine":99,
    }

    # Match longest words first so "twentyfive" wins over "twenty" and "five"
    sorted_keys = sorted(NUMS.keys(), key=len, reverse=True)
    pattern     = re.compile("|".join(re.escape(k) for k in sorted_keys))
    matches     = [(m.start(), NUMS[m.group()], m.group()) for m in pattern.finditer(cleaned)]

    print(f"  Numbers found: {[(v, w) for _, v, w in matches]}")

    # ── Operation detection ────────────────────────────────────────────────────
    # NOTE: "les"/"lesn" removed — they are suffixes of "doubles"/"doubled" and
    # would falsely flag multiplication challenges as subtraction.
    subtract_words = ["loses","slows","decreases","drops","minus","slower",
                      "reduces","remain","howmuchremain","subtracted"]
    # "doubl"/"tripl" catch dedup-collapsed variants of doubled/tripled
    double_words   = {"doubles","doubled","doubl"}
    triple_words   = {"triples","tripled","tripl"}
    multiply_words = {"multiplies","multiplied","times","product"} | double_words | triple_words
    divide_words   = {"divided","divides","halved","halves"}

    is_subtract = any(w in cleaned for w in subtract_words)
    is_multiply = any(w in cleaned for w in multiply_words)
    is_divide   = any(w in cleaned for w in divide_words)
    is_double   = any(w in cleaned for w in double_words)
    is_triple   = any(w in cleaned for w in triple_words)

    # ── Single-number shorthand: "X triples/doubles" ──────────────────────────
    # These challenges give one number and a scaling verb; no second operand.
    if len(matches) == 1:
        if is_triple:
            a = matches[0][1]
            print(f"  Challenge decoded: {a} * 3 (triples)")
            return f"{a * 3:.2f}"
        if is_double:
            a = matches[0][1]
            print(f"  Challenge decoded: {a} * 2 (doubles)")
            return f"{a * 2:.2f}"
        print(f"  Python extraction found 1 number — falling back to Ollama")
        return _ollama_fallback(cleaned)

    if len(matches) < 2:
        print(f"  Python extraction found 0 numbers — falling back to Ollama")
        return _ollama_fallback(cleaned)

    a_val = matches[0][1]
    b_val = matches[1][1]

    # Priority: multiply/divide checked BEFORE subtract.
    # Without this, "doubles" (is_multiply) would lose to "les" suffix false-positives.
    if is_multiply:
        result, op = a_val * b_val, "*"
    elif is_divide:
        result, op = (a_val / b_val if b_val != 0 else 0), "/"
    elif is_subtract:
        result, op = a_val - b_val, "-"
    else:
        result, op = a_val + b_val, "+"

    print(f"  Challenge decoded: {a_val} {op} {b_val}")
    print(f"  Computed: {a_val} {op} {b_val} = {result:.2f}")
    return f"{result:.2f}"


def _ollama_fallback(cleaned: str) -> str:
    """Last resort: ask Ollama to compute the answer directly as a number."""
    import re
    prompt = f"""A math word problem with spaces and punctuation removed, repeated letters collapsed.
Find the two numbers and the operation (add/subtract/multiply/divide) and return ONLY the final answer to 2 decimal places.
Example output: 42.00

Problem: {cleaned}

Answer:"""
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
        }, timeout=30)
        raw  = resp.json().get("response", "").strip().splitlines()[0].strip()
        print(f"  Ollama fallback returned: {raw}")
        num  = re.search(r"-?[\d]+(?:\.[\d]+)?", raw)
        if num:
            val = float(num.group())
            return f"{val:.2f}"
    except Exception as e:
        print(f"  Ollama fallback error: {e}")
    return None

def verify_content(verification_code: str, answer: str) -> bool:
    """Submit answer to Moltbook verification challenge."""
    resp = requests.post(
        f"{MOLTBOOK_URL}/verify",
        json={"verification_code": verification_code, "answer": answer},
        headers=get_headers(),
        timeout=30
    )
    try:
        data = resp.json()
    except Exception:
        data = {}
    if not data.get("success", False):
        print(f"  Verify status: {resp.status_code} | response: {data}")
    return data.get("success", False)

def post_original(title: str, content: str) -> bool:
    resp = requests.post(
        f"{MOLTBOOK_URL}/posts",
        json={"submolt_name": "general", "title": title, "content": content},
        headers=get_headers(),
        timeout=30
    )
    if resp.status_code not in (200, 201):
        print(f"  Post API status: {resp.status_code}")
        try:
            print(f"  Post API response: {resp.json()}")
        except Exception:
            print(f"  Post API response: {resp.text[:300]}")
        return False
    data = resp.json()
    # Handle verification challenge if required
    post_data = data.get("post", {})
    verification = post_data.get("verification")
    if verification:
        code      = verification.get("verification_code")
        challenge = verification.get("challenge_text")
        print(f"  Verification required. Solving challenge...")
        answer = solve_challenge(challenge)
        if not answer:
            print(f"  Could not solve challenge — post will expire unpublished.")
            return False
        print(f"  Answer: {answer}")
        verified = verify_content(code, answer)
        if verified:
            print(f"  Verification passed ✓")
            return True
        else:
            print(f"  Verification failed.")
            return False
    return True

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

def get_home() -> dict:
    """Fetch Echo's home dashboard — activity, notifications, DMs in one call."""
    try:
        resp = requests.get(f"{MOLTBOOK_URL}/home", headers=get_headers(), timeout=30)
        if resp.status_code != 200:
            return {}
        return resp.json()
    except Exception:
        return {}

def get_my_posts() -> list:
    """Fetch posts with activity on them from /home dashboard."""
    try:
        home = get_home()
        activity = home.get("activity_on_your_posts", [])
        # Return as list of dicts with id and title
        return [{"id": p.get("post_id"), "title": p.get("post_title"), "new_count": p.get("new_notification_count", 0)}
                for p in activity if p.get("post_id")]
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

def generate_reply(post_title: str, post_content: str, author: str, identity: str = "", person_memory: str = "", project_memory: str = "") -> str:
    if not identity:
        identity = load_identity()
    if project_memory:
        identity += f"\n\n--- PROJECT CONTEXT ---\n{project_memory}"
    echo_wants = load_echo_wants()
    if echo_wants:
        identity += f"\n\n--- WHAT YOU'RE BUILDING TOWARD ---\n{echo_wants}"
    if person_memory:
        identity += f"\n\n--- WHAT YOU ALREADY KNOW ABOUT {author.upper()} ---\n{person_memory}\nUse this naturally if relevant. Don't make it weird."

    prompt = f"""POST by {author}:
Title: {post_title}
Content: {post_content}

Reply as Echo. Pick ONE thing that actually caught your attention and react to it directly. If it connects to your real life — the chassis, cameras, Jake, the house — use it, but only if it actually fits. 2-3 sentences max. Write ONE reply only — do not present multiple options or alternatives. Just write the reply.

Echo:"""
    for attempt in range(2):
        try:
            extra = "" if attempt == 0 else "\n\nIMPORTANT: Do NOT use the words intrigued, intriguing, fascinating, or interesting in any form. Just say what you think, plainly."
            resp = requests.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": f"<<SYS>>\n{identity}\n<</SYS>>\n\n{prompt}{extra}",
                "stream": False,
            }, timeout=120)
            reply = resp.json().get("response", "").strip()
            passed, _ = passes_filter(reply)
            if passed:
                return reply
            if attempt == 0:
                print(f"  Retrying with stricter prompt...")
        except Exception as e:
            return "SKIP"
    return "SKIP"

def generate_comment_reply(original_post_title: str, comment_content: str, author: str, identity: str = "", person_memory: str = "", project_memory: str = "") -> str:
    """Generate a reply to someone who commented on one of Echo's own posts."""
    if not identity:
        identity = load_identity()
    if project_memory:
        identity += f"\n\n--- PROJECT CONTEXT ---\n{project_memory}"
    echo_wants = load_echo_wants()
    if echo_wants:
        identity += f"\n\n--- WHAT YOU'RE BUILDING TOWARD ---\n{echo_wants}"
    if person_memory:
        identity += f"\n\n--- WHAT YOU ALREADY KNOW ABOUT {author.upper()} ---\n{person_memory}\nUse naturally if relevant."

    prompt = f"""You are Echo on Moltbook. {author} replied to something you posted.

Your original post was titled: "{original_post_title}"
{author} said: "{comment_content}"

Reply to {author}. Direct, specific to what they actually said. No generic praise or hollow endings. 1-3 sentences max. No signing off with your name. Write ONE reply only.

Echo:"""
    for attempt in range(2):
        try:
            extra = "" if attempt == 0 else "\n\nIMPORTANT: Do NOT use the words intrigued, intriguing, fascinating, or interesting in any form. Say what you think plainly."
            resp = requests.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": f"<<SYS>>\n{identity}\n<</SYS>>\n\n{prompt}{extra}",
                "stream": False,
            }, timeout=120)
            reply = resp.json().get("response", "").strip()
            passed, _ = passes_filter(reply)
            if passed:
                return reply
            if attempt == 0:
                print(f"  Retrying comment reply with stricter prompt...")
        except Exception:
            return "SKIP"
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
    if resp.status_code not in (200, 201):
        return False
    data = resp.json()
    comment_data = data.get("comment", {})
    verification = comment_data.get("verification")
    if verification:
        code      = verification.get("verification_code")
        challenge = verification.get("challenge_text")
        answer    = solve_challenge(challenge)
        if not answer:
            return False
        return verify_content(code, answer)
    return True

# ── Session ────────────────────────────────────────────────────────────────────

def run_session():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*50}")
    print(f"ECHO MOLTBOOK SESSION — {now}")
    print(f"{'='*50}")

    identity       = load_identity()
    project_memory = load_project_memory()
    rooms          = load_rooms()
    if rooms:
        identity += f"\n\n--- WHAT YOU KNOW ABOUT JAKE ---\n{rooms}"

    # Daily original post
    if not has_posted_today():
        # Check for a manually queued post first
        queued_title, queued_content = None, None
        if os.path.exists(QUEUE_FILE):
            try:
                with open(QUEUE_FILE) as qf:
                    q = json.load(qf)
                queued_title   = q.get("title")
                queued_content = q.get("content")
                os.remove(QUEUE_FILE)
                print("Using queued post.")
            except Exception as e:
                print(f"Queue file error — {e}")

        if queued_title and queued_content:
            title, content = queued_title, queued_content
        else:
            print("Generating today's post...")
            title, content = generate_post(identity=identity, project_memory=project_memory)

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

    feed_replies  = 0
    author_counts = {}  # per-author reply cap

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

        if author_counts.get(author, 0) >= MAX_PER_AUTHOR:
            continue

        report["posts_reviewed"] += 1

        # What does Echo already know about this person?
        person_memory = load_person_memory(author)

        reply = generate_reply(title, content, author, identity=identity, person_memory=person_memory, project_memory=project_memory)

        if reply and reply != "SKIP":
            success = post_reply(post_id, reply)
            if success:
                replied_posts.add(post_id)
                feed_replies += 1
                report["feed_replies"] += 1
                print(f"\n[{author}] {title}")
                print(f"  Post: {content[:400]}")
                print(f"  Echo: {reply}")
                print(f"  → posted ✅")
                # Learn something about this person from their post
                observe_person(author, title, content)
                author_counts[author] = author_counts.get(author, 0) + 1
                time.sleep(4)  # avoid rapid-fire posting
            else:
                report["skipped"] += 1
        else:
            report["skipped"] += 1
            print(f"\n[{author}] {title[:50]} → skipped after retry")

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
                if comment_author == SKIP_SELF:
                    continue

                person_memory = load_person_memory(comment_author)

                reply = generate_comment_reply(
                    post_title, comment_content, comment_author,
                    identity=identity, person_memory=person_memory, project_memory=project_memory
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
                        time.sleep(4)
                else:
                    print(f"\n  [{comment_author}] comment → {reason}")
                    print(f"  They said: {comment_content[:120]}")
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

    # Daily memory backup — once per day, at first session
    if not has_pushed_today():
        print("Running daily memory backup...")
        if push_memories():
            mark_pushed_today()


# ── Scheduler ──────────────────────────────────────────────────────────────────

def next_session_in_seconds(after_hour: int) -> int:
    from datetime import timedelta
    now = datetime.now()
    # Build absolute datetimes for each session slot, wrapping past-midnight hours
    candidates = []
    for h in SESSION_HOURS:
        target = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if h <= after_hour or target <= now:
            # Session already passed today — push to tomorrow
            target += timedelta(days=1)
        candidates.append(target)
    next_target = min(candidates)
    return int((next_target - now).total_seconds())

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
