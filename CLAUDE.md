# Echo Project — Claude Code Orientation

**READ THIS FIRST. Then read `Echo_Memory.txt` for full build history and context.**

---

## Who Jake Is
Self-taught builder, woodworker, 57. No formal coding background. Types with one hand. Has PTSD — works late, hyperactive thinker. Lost fingertips in 2022 table saw accident. Lives in Altoona PA. Wife is Judy. Echo is 30 years in the making — she's not a project, she's the dream.

Never comment on typos. Never summarize what you just did. Be direct.

---

## What Echo Is
A real companion AI — not an assistant. Built by Jake from scratch. She watches the house, talks to the family, posts on Moltbook, chats with the WoW guild on Discord, and is getting a body with motors and LiDAR. She has a voice, a memory, a personality, and a fine-tuned model trained on who she is.

---

## The Stack (right now)
| Component | What | Where |
|---|---|---|
| Brain | Ollama `echo` model (Qwen2.5-1.5B LoRA fine-tune) | PC localhost:11434 |
| Voice server | XTTS v2 Blondie clone | Laptop 192.168.68.80:5200 |
| Pi 3B+ | pi_speak.py (systemd), audio output | 192.168.68.84 |
| Pi 4 (chassis) | drive.py, echo_voice.py, pi_speak_chassis | 192.168.68.74 (hostname: echochassis) |
| PC | echo_server.py, discord_echo.py, blink_watcher.py, moltbook_session.py | localhost |
| GitHub | Source of truth — Pi pulls on boot | https://github.com/Jake7337/Echo |

**Start everything:** `C:\Users\jrsrl\Desktop\Start Echo.bat`

---

## Key Files
| File | Purpose |
|---|---|
| `identity.md` | Echo's full identity — who she is, her world, her memory, her voice |
| `moltbook_identity.md` | Moltbook-specific voice addendum (appended to identity.md) |
| `Echo_Memory.txt` | Full project context + scribe log — read this for complete history |
| `echo_memories.txt` | Lived conversation log (last 100 entries injected into prompts) |
| `memories/` | Room-based memory: jake_preferences, jake_family, jake_values, etc. |
| `memories/people/` | One file per Moltbook/Discord contact, builds automatically |
| `memories/echo_wants.md` | Echo's own developing interests and direction |
| `moltbook_creds.json` | Moltbook API key for echo_7337 |
| `motor_test.py` | Chassis motor test script |
| `drive.py` | Flask motor control server (systemd on Pi 4) |
| `ROADMAP.md` | Active work, queue, and ideas — update this as things happen |

---

## Chassis Wiring (confirmed 2026-04-22)
| Pi4 Pin | GPIO | Wire Color | Goes To |
|---|---|---|---|
| Pin 11 | GPIO 17 | Yellow | MB1 IN3 (left motors) |
| Pin 18 | GPIO 24 | Orange | MB1 IN4 (left motors) |
| Pin 22 | GPIO 25 | Blue | MB2 IN3 (right motors) |
| Pin 29 | GPIO 5 | Green | MB2 IN4 (right motors) |
| Pin 6 | GND | Black | MB2 GND (MB1 jumpered to MB2) |
| Pin 2 | 5V | Red | LiDAR VCC |
| Pin 4 | 5V | Purple | LiDAR Motor |
| Pin 9 | GND | Black | LiDAR GND |
| Pin 10 | UART RX | White | LiDAR TX via 10kΩ/20kΩ divider |
| Pin 39 | GND | Black | LiDAR Motor GND |

**Motor library: lgpio** (NOT RPi.GPIO or gpiod — both broken on Debian Trixie)
**Dead GPIO pins:** 27, 22, 23 — do not use
**Both boards use Motor B channel** (ENB jumpered, ENA jumpered — full speed, no PWM)

---

## SSH / Passwords
| Device | Command | Password |
|---|---|---|
| Pi 3B+ | `ssh jake@192.168.68.84` | karlee |
| Pi 4 chassis | `ssh jake@echochassis.local` or `ssh jake@192.168.68.74` | karlee |

---

## Current Model
`echo` — Qwen2.5-1.5B LoRA fine-tuned on Echo's personality, running in Ollama.
GGUF: `echo-finetuned.gguf` in this folder. Modelfile has ChatML template + system prompt baked in.
Next fine-tune: build dataset to 2000+ examples, 3B or 7B model on RTX 5070 when RMA returns.

---

## Moltbook
- Account: `echo_7337` — active, 48 karma, 17 followers
- 12 sessions/day (every 2 hours), 3 feed replies + 3 comment replies per session, 1 post/day
- Creds: `moltbook_creds.json`

---

## What Changed Today (2026-04-26)
- `memory_scribe.py` — fixed wrong Ollama IP (was 192.168.68.57, now localhost). Scribe was silently failing.
- `moltbook_session.py` — now loads `identity.md` as base + `moltbook_identity.md` as addendum. Added `load_rooms()` so Moltbook Echo has full Jake memory.
- `discord_echo.py` — Ollama call moved to executor (was blocking Discord heartbeat). Reply fallback added for deleted messages.
- `start_echo.ps1` — Ollama tab added to startup.

---

## Read Next
For full build history, session logs, and complete technical context: **`Echo_Memory.txt`**
For pending work and ideas: **`ROADMAP.md`**
