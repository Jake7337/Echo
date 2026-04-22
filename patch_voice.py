#!/usr/bin/env python3
# Patches echo_voice.py to add drive command support

import re

with open("echo_voice.py", "r") as f:
    code = f.read()

# 1. Add DRIVE_SERVER constant after OLLAMA_URL line
drive_constant = 'DRIVE_SERVER = "http://192.168.68.65:5102"'
if "DRIVE_SERVER" not in code:
    code = re.sub(
        r'(OLLAMA_URL\s*=\s*[^\n]+\n)',
        r'\1' + drive_constant + '\n',
        code
    )
    print("Added DRIVE_SERVER constant")
else:
    print("DRIVE_SERVER already present")

# 2. Add drive functions before def main()
drive_functions = '''
DRIVE_KEYWORDS = {
    "forward":    ("forward", 2),
    "go forward": ("forward", 2),
    "move forward": ("forward", 2),
    "drive forward": ("forward", 2),
    "backward":   ("backward", 2),
    "go backward": ("backward", 2),
    "reverse":    ("backward", 2),
    "go back":    ("backward", 2),
    "turn left":  ("left", 1.5),
    "go left":    ("left", 1.5),
    "turn right": ("right", 1.5),
    "go right":   ("right", 1.5),
    "stop":       ("stop", 0),
    "stop moving": ("stop", 0),
}

def parse_drive_command(text):
    t = text.lower().strip()
    for phrase, (direction, duration) in DRIVE_KEYWORDS.items():
        if phrase in t:
            return direction, duration
    return None, None

def send_drive(direction, duration):
    try:
        requests.post(
            f"{DRIVE_SERVER}/drive",
            json={"direction": direction, "duration": duration},
            timeout=3
        )
    except Exception as e:
        print(f"[drive] Error: {e}")

'''

if "DRIVE_KEYWORDS" not in code:
    code = code.replace("def main():", drive_functions + "def main():")
    print("Added drive functions")
else:
    print("Drive functions already present")

# 3. Add drive detection in main loop after "if not user_input:" block
drive_check = '''
        direction, duration = parse_drive_command(user_input)
        if direction:
            print(f"[drive] {direction} for {duration}s")
            send_drive(direction, duration)
            speak(f"On it.", voice)
            conversations = add_exchange(conversations, user_input, "On it.")
            save_memory(conversations)
            continue

'''

if "parse_drive_command" not in code or "direction, duration = parse_drive_command" not in code:
    code = code.replace(
        "        if not user_input:\n            continue\n",
        "        if not user_input:\n            continue\n" + drive_check
    )
    print("Added drive detection in main loop")
else:
    print("Drive detection already present")

with open("echo_voice.py", "w") as f:
    f.write(code)

print("Done — echo_voice.py patched.")
