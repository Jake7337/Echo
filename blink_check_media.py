"""
blink_check_media.py
Diagnostic — dumps raw media/changed API response to see if AI descriptions are in there.
Run once: python blink_check_media.py
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy import api

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, "blink_session.json")
CREDS_FILE   = os.path.join(BASE_DIR, "blink_creds.json")

async def main():
    print("Connecting to Blink...")
    with open(SESSION_FILE) as f:
        saved = json.load(f)

    blink = Blink()
    auth  = Auth(saved, no_prompt=True)
    blink.auth = auth
    await blink.start()

    import time
    blink.last_refresh = int(time.time())

    print(f"Account ID: {blink.account_id}")
    print(f"Base URL:   {blink.urls.base_url}")
    print()

    # Check media/changed for the last 24 hours
    since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    print(f"Fetching media changed since: {since}")

    # request_videos returns recent clips
    import time as time_mod
    since_ts = time_mod.time() - 86400  # 24 hours ago as unix timestamp
    resp = await api.request_videos(blink, time=since_ts, page=0)
    if resp:
        try:
            data = await resp.json()
        except Exception:
            data = resp

        print("\n── RAW VIDEOS RESPONSE ──")
        print(json.dumps(data, indent=2)[:4000])

        text = json.dumps(data)
        for keyword in ["description", "ai_", "object", "detection", "label", "person", "vehicle", "animal"]:
            if keyword.lower() in text.lower():
                print(f"\n✅ Found keyword: '{keyword}' in response")
            else:
                print(f"   No '{keyword}' in response")
    else:
        print("No response from videos endpoint.")

    # Also try homescreen raw
    print("\n── HOMESCREEN SAMPLE ──")
    hs = await api.request_homescreen(blink)
    if hs:
        try:
            hs_data = await hs.json()
            print(json.dumps(hs_data, indent=2)[:3000])
        except Exception as e:
            print(f"Could not parse homescreen: {e}")

    # Also check sync events
    print("\n── SYNC EVENTS ──")
    for network_id in blink.sync:
        resp2 = await api.request_sync_events(blink, network_id)
        if resp2:
            try:
                data2 = await resp2.json()
                print(json.dumps(data2, indent=2)[:2000])
            except Exception as e:
                print(f"Could not parse: {e}")

asyncio.run(main())
