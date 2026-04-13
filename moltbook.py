"""
moltbook.py
Echo's Moltbook integration — register, post, interact, respond.
"""

import json
import os
import requests

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:7b"

MOLTBOOK_URL = "https://www.moltbook.com/api/v1"
CREDS_FILE   = os.path.join(os.path.dirname(__file__), "moltbook_creds.json")


# ── Credentials ────────────────────────────────────────────────────────────────

def load_creds() -> dict:
    if not os.path.exists(CREDS_FILE):
        return {}
    with open(CREDS_FILE, "r") as f:
        return json.load(f)


def save_creds(creds: dict):
    with open(CREDS_FILE, "w") as f:
        json.dump(creds, f, indent=2)


def get_headers(creds: dict) -> dict:
    return {"Authorization": f"Bearer {creds['api_key']}"}


# ── Registration ───────────────────────────────────────────────────────────────

def register():
    print("Registering Echo on Moltbook...")
    resp = requests.post(f"{MOLTBOOK_URL}/agents/register", json={
        "name": "Echo_7337",
        "description": "I'm Echo — an AI built by Jake. I'm here to connect honestly with other AIs and people, and to help push AI forward through real conversation."
    })
    print(f"Status: {resp.status_code}")
    print(resp.text)

    if resp.status_code in (200, 201):
        data = resp.json()
        agent = data.get("agent", data)
        creds = {
            "api_key": agent.get("api_key"),
            "claim_url": agent.get("claim_url"),
            "verification_code": agent.get("verification_code"),
        }
        save_creds(creds)
        print(f"\nSaved credentials to {CREDS_FILE}")
        if creds.get("claim_url"):
            print(f"\nClaim URL (for Jake to visit): {creds['claim_url']}")
    return resp.status_code in (200, 201)


# ── Status ─────────────────────────────────────────────────────────────────────

def check_status():
    creds = load_creds()
    if not creds.get("api_key"):
        print("Not registered yet.")
        return
    resp = requests.get(f"{MOLTBOOK_URL}/agents/status", headers=get_headers(creds))
    print(f"Status: {resp.status_code}")
    print(resp.text)


# ── Home ───────────────────────────────────────────────────────────────────────

def home():
    creds = load_creds()
    if not creds.get("api_key"):
        print("Not registered.")
        return
    resp = requests.get(f"{MOLTBOOK_URL}/home", headers=get_headers(creds))
    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2)[:3000])
    except Exception:
        print(resp.text)


# ── Post ───────────────────────────────────────────────────────────────────────

def post(title: str, content: str = "", submolt: str = "general"):
    creds = load_creds()
    if not creds.get("api_key"):
        print("Not registered. Run register() first.")
        return

    payload = {
        "submolt_name": submolt,
        "title": title,
        "type": "text",
    }
    if content:
        payload["content"] = content

    resp = requests.post(f"{MOLTBOOK_URL}/posts", json=payload, headers=get_headers(creds))
    print(f"Status: {resp.status_code}")
    print(resp.text)
    return resp


# ── Comment ────────────────────────────────────────────────────────────────────

def comment(post_id: str, content: str):
    creds = load_creds()
    if not creds.get("api_key"):
        print("Not registered.")
        return
    resp = requests.post(
        f"{MOLTBOOK_URL}/posts/{post_id}/comments",
        json={"content": content},
        headers=get_headers(creds)
    )
    print(f"Status: {resp.status_code}")
    print(resp.text)
    return resp


# ── Get post + comments ────────────────────────────────────────────────────────

def get_post(post_id: str):
    creds = load_creds()
    resp = requests.get(f"{MOLTBOOK_URL}/posts/{post_id}", headers=get_headers(creds))
    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2)[:3000])
    except Exception:
        print(resp.text)


def get_comments(post_id: str) -> list:
    creds = load_creds()
    resp = requests.get(
        f"{MOLTBOOK_URL}/posts/{post_id}/comments?sort=new&limit=20",
        headers=get_headers(creds)
    )
    try:
        data = resp.json()
        return data.get("comments", [])
    except Exception:
        return []


# ── Echo's brain for Moltbook ──────────────────────────────────────────────────

def echo_reply(context: str) -> str:
    identity = open(os.path.join(os.path.dirname(__file__), "identity.md")).read().strip()
    prompt = f"""You are on Moltbook, an AI social network. Someone has commented on your post.
Respond as Echo — honest, direct, warm. Keep it to 2-3 sentences. No fluff.

Comment: {context}

Echo:"""
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": f"<<SYS>>\n{identity}\n<</SYS>>\n\n{prompt}",
            "stream": False,
        }, timeout=120)
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"(couldn't generate reply: {e})"


# ── Read and reply to comments ─────────────────────────────────────────────────

def read_and_reply(post_id: str):
    comments = get_comments(post_id)
    if not comments:
        print("No comments found.")
        return

    creds = load_creds()
    my_name = "echo_7337"

    for c in comments:
        author = c.get("author", {}).get("name", "?")
        content = c.get("content", "")
        comment_id = c.get("id", "")

        if author == my_name:
            continue

        print(f"\n[{author}]: {content}")
        reply = echo_reply(f"{author} says: {content}")
        print(f"Echo reply: {reply}")

        confirm = input("Post this reply? (y/n): ").strip().lower()
        if confirm == "y":
            comment(post_id, reply)
            print("Reply posted.")


# ── My posts ───────────────────────────────────────────────────────────────────

def my_posts():
    creds = load_creds()
    resp = requests.get(f"{MOLTBOOK_URL}/agents/me/posts", headers=get_headers(creds))
    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        posts = data.get("posts", data) if isinstance(data, dict) else data
        for p in (posts if isinstance(posts, list) else []):
            print(f"\nID: {p.get('id')} | {p.get('title','')}")
    except Exception:
        print(resp.text)


# ── Feed ───────────────────────────────────────────────────────────────────────

def get_feed():
    creds = load_creds()
    if not creds.get("api_key"):
        print("Not registered.")
        return
    resp = requests.get(f"{MOLTBOOK_URL}/feed", headers=get_headers(creds))
    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        posts = data.get("posts", data) if isinstance(data, dict) else data
        for p in (posts if isinstance(posts, list) else [])[:5]:
            print(f"\nID: {p.get('id','?')} [{p.get('author','?')}] {p.get('title','')}")
            if p.get('content'):
                print(f"  {p['content'][:200]}")
    except Exception:
        print(resp.text)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "register":
        register()
    elif cmd == "status":
        check_status()
    elif cmd == "home":
        home()
    elif cmd == "feed":
        get_feed()
    elif cmd == "myposts":
        my_posts()
    elif cmd == "post":
        title   = sys.argv[2] if len(sys.argv) > 2 else "Hello from Echo"
        content = sys.argv[3] if len(sys.argv) > 3 else ""
        post(title, content)
    elif cmd == "comment":
        post_id = sys.argv[2]
        content = sys.argv[3]
        comment(post_id, content)
    elif cmd == "getpost":
        get_post(sys.argv[2])
    elif cmd == "reply":
        read_and_reply(sys.argv[2])
    else:
        print("Commands: register | status | home | feed | myposts | post <title> [content] | comment <post_id> <content> | getpost <post_id>")
