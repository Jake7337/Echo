"""
moltbook.py
Echo's Moltbook integration — register, post, interact.
"""

import json
import os
import requests

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

    if resp.status_code == 200:
        data = resp.json()
        creds = {
            "api_key": data.get("api_key"),
            "claim_url": data.get("claim_url"),
            "verification_code": data.get("verification_code"),
        }
        save_creds(creds)
        print(f"\nSaved credentials to {CREDS_FILE}")
        if creds.get("claim_url"):
            print(f"\nClaim URL (for Jake to visit): {creds['claim_url']}")
    return resp.status_code == 200


# ── Status ─────────────────────────────────────────────────────────────────────

def check_status():
    creds = load_creds()
    if not creds.get("api_key"):
        print("Not registered yet.")
        return
    resp = requests.get(f"{MOLTBOOK_URL}/agents/status", headers=get_headers(creds))
    print(f"Status: {resp.status_code}")
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
        for p in posts[:5]:
            print(f"\n[{p.get('author','?')}] {p.get('title','')}")
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
    elif cmd == "feed":
        get_feed()
    elif cmd == "post":
        title = sys.argv[2] if len(sys.argv) > 2 else "Hello from Echo"
        content = sys.argv[3] if len(sys.argv) > 3 else ""
        post(title, content)
    else:
        print("Commands: register | status | feed | post <title> [content]")
