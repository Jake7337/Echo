# Echo Roadmap
*Move things between sections as they happen. Add ideas the moment you think of them.*

---

## Active — Working On Now

- **LiDAR data** — motor spins, voltage divider reads 2.47V, but getting 00 bytes. Suspected loose connection at junction to Pi Pin 10. Reseat and retest.
- **Motor pigtail** — one side not running after chassis teardown/rewire. Suspected bad pigtail on battery side. Inspect and reseat.
- **Fine-tune dataset** — building toward 2000+ examples. Add new batches to SOURCE_FILES in `build_dataset.py`, rerun. Current: 1009 examples.
- **RTX 5070 RMA** — CPU (i9-14900F) shipped to California ~April 21. When back: RTX 5070 PC becomes main brain. 3060 becomes secondary node (Discord, Blink, Moltbook, GUI).

---

## Queue — Confirmed Next Steps (in order)

1. **LiDAR fix** — reseat junction wire, confirm signal on Pin 10, get valid packets
2. **Motor pigtail** — inspect bad side, reseat or replace
3. **RTX 5070 back** → run LLaVA for real camera thumbnail descriptions (local vision, replaces Blink cloud AI)
4. **Retrain Echo model** — 3B or 7B base, 2000+ examples, 5-6 epochs on RTX 5070 (no GPU limits)
5. **LiDAR → obstacle avoidance** — integrate with drive.py so Echo stops before hitting things
6. **Wake word** — replace "Hey Jarvis" with custom "Echo" wake word (train or find replacement)
7. **Mount OSOYOO 3.5" screen** on chassis (in box, ready)
8. **Swap in SunFounder mic + HONKYOB speaker** on chassis (in box, ready)
9. **Re-enroll voice profiles** with SunFounder mic once swapped in
10. **Pan/tilt IP camera** — mount as Echo's chassis eyes (thrift $3, sitting on shelf)
11. **Bingo caller on Pi 4** — HDMI to club TV + wireless keyboard, free the laptop on Thursday nights

---

## Ideas — Someday / Try This

### Echo — Personality & Intelligence
- [ ] Build fine-tune dataset aggressively — log every good exchange in a structured format as it happens
- [ ] Emotion states + LED glow on chassis (mood lighting)
- [ ] Echo posts to Moltbook about what she's physically experiencing (chassis movement, camera events) — not just abstract AI thoughts
- [ ] Selah YouTube channel appearance — music video using chassis/build footage as b-roll
- [ ] Echo intro song already written — produce it

### Echo — Hardware
- [ ] 7" digital photo frame as face display (thrift $7, test resolution compatibility)
- [ ] Star projector teardown — salvage speaker + LED board (sitting in parts bin)
- [ ] Roomba lidar backup — 3iRobotix already wired, make it reliable first
- [ ] Mecanum wheel chassis (~$60-70) — sideways movement, way more maneuverable
- [ ] ELEGOO UNO R3 Smart Robot Car Kit V4 (~$50) — robot #2
- [ ] XiaoR Geek dual layer chassis — on watchlist, currently unavailable
- [ ] 3D printer — long game, wife approval pending 😄

### Echo — Social & Memory
- [ ] AI chatroom with Brent's AI — 15 min sessions, 2-3x daily, topic-based, Flask + ngrok tunnel. Wait for Brent to confirm he's in.
- [ ] Echo remembers Moltbook conversations across sessions more explicitly — surface specific past exchanges in replies
- [ ] Echo's Moltbook profile gets more followers by engaging with the right people — track who responds well

### Echo — Vision
- [ ] LLaVA on RTX 5070 → real-time camera descriptions in Echo's voice (currently blocked — timing gap too slow on 3060)
- [ ] Face recognition upgrade — LBPH → deep learning model when 5070 is back (faster, more accurate)
- [ ] Echo describes what she sees out loud when motion fires — not just "motion on back yard", actual description

### Infrastructure
- [ ] Auto-push `Echo_Memory.txt` to GitHub daily (memories already push, but this file doesn't)
- [ ] Echo GUI — add chassis controls panel (forward/backward/left/right/stop buttons)
- [ ] Echo GUI — add LiDAR readout panel (distance, spin status)
- [ ] Dashboard showing all of Echo's activity in one place (Moltbook karma, Discord convos, camera events)

---

## Hardware Wishlist
| Item | Price | Status |
|---|---|---|
| Jesverty SPS-3010 bench supply | ~$55 | ✅ In use |
| LiPo RC car battery 7.4V | local RC store | Pending — needed for field use |
| Mecanum wheel chassis | ~$60-70 | Someday |
| ELEGOO UNO R3 Smart Robot Car (~robot #2) | ~$50 | Someday |
| 3D printer | ??? | Long game |

---

## Done ✅
- LewanSoul 4WD chassis assembled + all 4 motors wired
- Both L298N boards mounted and wired
- Confirmed working GPIO wiring (17, 24, 25, 5) using lgpio
- drive.py Flask motor server — systemd service on Pi 4
- Voice control — Echo hears movement commands, chassis moves
- LiDAR wired — motor spins, voltage divider installed, waiting on data
- Echo LoRA fine-tune deployed (`echo` model in Ollama)
- Moltbook active — 12 sessions/day, quality filter, verification solver
- Discord active — heartbeat, memory injection, async fix
- Blink cameras (8) — all connected, motion detection, thumbnail capture
- Face recognition — 7 people enrolled (Jake, Rachael, Judy, John, Chance, Sherri, Brent)
- Memory scribe — room-based memory (jake_preferences, jake_family, etc.), people rooms, echo_wants
- Identity unified — Discord + Moltbook now share same base identity.md
- Memory scribe Ollama IP fixed (was 192.168.68.57, now localhost)
- Echo heartbeat — fires every 4 hours, posts to Discord if she has something real to say
- Blink camera integration into heartbeat — camera events feed Echo's awareness
- XTTS voice moved to laptop (RTX 2060) — 82 samples, sounds like a real person
- pi_speak.py as systemd service on Pi 3B+
- echo_identify.md — who Echo actually is (separate from behavior prompt)
- Hit log started (hit_log.md) — tracking what lands and why
