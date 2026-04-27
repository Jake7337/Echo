"""
face_enroll.py
Live webcam face enrollment for Echo's face recognition system.
Guided poses, live landmark overlay, auto-captures on face detection.
Saves to known_faces/<name>/ — works directly with echo_identify.py.

Usage: python face_enroll.py
Controls: SPACE to start / continue, ESC to quit, BACKSPACE to fix name
"""

import cv2
import os
import time
import face_recognition
import numpy as np
from pathlib import Path

BASE_DIR    = Path(os.path.dirname(os.path.abspath(__file__)))
FACES_DIR   = BASE_DIR / "known_faces"

# Guided poses — (instruction, frames to capture)
POSES = [
    ("Look straight at the camera",   35),
    ("Turn slightly to your LEFT",    25),
    ("Turn slightly to your RIGHT",   25),
    ("Tilt your head UP slightly",    20),
    ("Tilt your head DOWN slightly",  20),
    ("Straight again — relax",        25),
]

TOTAL_FRAMES = sum(p[1] for p in POSES)

# Colors (BGR)
CYAN  = (220, 210, 0)
GREEN = (80, 220, 80)
WHITE = (210, 210, 210)
DIM   = (90,  90, 110)
RED   = (60,  60, 200)
PINK  = (180,  0, 200)
BLACK = (0, 0, 0)

FONT  = cv2.FONT_HERSHEY_SIMPLEX
FONT2 = cv2.FONT_HERSHEY_DUPLEX


def text_center(frame, text, y, scale, color, thickness=1):
    h, w = frame.shape[:2]
    tw   = cv2.getTextSize(text, FONT, scale, thickness)[0][0]
    cv2.putText(frame, text, ((w - tw) // 2, y), FONT, scale, color, thickness, cv2.LINE_AA)


def draw_overlay(frame, locations, landmarks):
    """Draw face bounding boxes and landmark mesh."""
    for (top, right, bottom, left) in locations:
        cv2.rectangle(frame, (left, top), (right, bottom), CYAN, 2)
        cv2.rectangle(frame, (left, top - 2), (right, top), CYAN, -1)

    for lm in landmarks:
        for feature, pts in lm.items():
            arr = np.array(pts, dtype=np.int32)
            closed = feature in ("left_eye", "right_eye", "top_lip", "bottom_lip")
            cv2.polylines(frame, [arr], closed, GREEN, 1, cv2.LINE_AA)
            for p in pts:
                cv2.circle(frame, p, 2, GREEN, -1, cv2.LINE_AA)


def bar(frame, current, total, y, bar_w=320, bar_h=10):
    h, w  = frame.shape[:2]
    x     = (w - bar_w) // 2
    cv2.rectangle(frame, (x, y), (x + bar_w, y + bar_h), (30, 30, 40), -1)
    fill = int(bar_w * min(current / total, 1.0))
    if fill:
        cv2.rectangle(frame, (x, y), (x + fill, y + bar_h), CYAN, -1)


def dark_bar(frame, y, h_px=65):
    overlay = frame.copy()
    fh, fw  = frame.shape[:2]
    cv2.rectangle(overlay, (0, y), (fw, y + h_px), BLACK, -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)


def run():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    IDLE, NAME, COUNTDOWN, POSE, DONE = "idle", "name", "countdown", "pose", "done"
    state        = IDLE
    person_name  = ""
    pose_idx     = 0
    captured     = 0
    save_dir     = None
    last_capture = 0.0
    countdown_start = 0.0
    COUNTDOWN_SEC   = 3

    # Cached face data — updated every 3rd frame to keep UI smooth
    tick             = 0
    cached_locs      = []
    cached_landmarks = []

    cv2.namedWindow("Echo Face Enrollment", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Echo Face Enrollment", 1280, 720)

    while True:
        ret, raw = cap.read()
        if not ret:
            break

        raw  = cv2.flip(raw, 1)       # mirror so it feels natural
        frame = raw.copy()            # draw on this — raw stays clean for saving
        fh, fw = frame.shape[:2]
        tick  += 1

        # ── Face detection every 3rd frame ────────────────────────────────────
        if tick % 3 == 0:
            small = cv2.resize(raw, (0, 0), fx=0.5, fy=0.5)
            rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            locs  = face_recognition.face_locations(rgb, model="hog")
            cached_locs = [(t*2, r*2, b*2, l*2) for (t, r, b, l) in locs]
            if cached_locs:
                cached_landmarks = face_recognition.face_landmarks(
                    cv2.cvtColor(raw, cv2.COLOR_BGR2RGB), cached_locs
                )
            else:
                cached_landmarks = []

        face_found = len(cached_locs) > 0

        # ── Draw face overlay (always) ─────────────────────────────────────────
        if cached_landmarks:
            draw_overlay(frame, cached_locs, cached_landmarks)
        elif cached_locs:
            draw_overlay(frame, cached_locs, [])

        # ── Dark bars top + bottom ─────────────────────────────────────────────
        dark_bar(frame, 0, 55)
        dark_bar(frame, fh - 70, 70)

        # Header
        cv2.putText(frame, "ECHO  FACE  ENROLLMENT", (22, 36),
                    FONT, 0.65, CYAN, 1, cv2.LINE_AA)

        # ── IDLE ──────────────────────────────────────────────────────────────
        if state == IDLE:
            text_center(frame, "Press SPACE to begin", fh // 2 - 20, 1.0, WHITE, 2)
            text_center(frame, "ESC to quit", fh // 2 + 40, 0.5, DIM, 1)

        # ── NAME ENTRY ────────────────────────────────────────────────────────
        elif state == NAME:
            text_center(frame, "Who is this?", fh // 2 - 60, 0.75, DIM, 1)
            display = (person_name + "|").upper()
            text_center(frame, display, fh // 2 + 10, 1.4, WHITE, 2)
            text_center(frame, "Type name  |  ENTER to confirm  |  BACKSPACE to fix",
                        fh // 2 + 70, 0.48, DIM, 1)

        # ── COUNTDOWN ─────────────────────────────────────────────────────────
        elif state == COUNTDOWN:
            elapsed   = time.time() - countdown_start
            remaining = COUNTDOWN_SEC - int(elapsed)
            if remaining <= 0:
                state    = POSE
                captured = 0
            else:
                pose_label = POSES[pose_idx][0]
                text_center(frame, pose_label, fh // 2 - 40, 0.85, WHITE, 2)
                text_center(frame, f"Starting in  {remaining}...", fh // 2 + 30, 1.0, CYAN, 2)

        # ── POSE CAPTURE ──────────────────────────────────────────────────────
        elif state == POSE:
            pose_label, pose_target = POSES[pose_idx]

            # Instruction
            text_center(frame, pose_label, fh // 2 - 50, 0.9, WHITE, 2)

            # Face status
            if face_found:
                status, scol = "Face locked in  \xe2\x80\x94  hold still", GREEN
            else:
                status, scol = "Move into frame", RED
            text_center(frame, status, fh // 2 + 10, 0.6, scol, 1)

            # Progress bar
            bar(frame, captured, pose_target, fh // 2 + 40)
            text_center(frame, f"{captured} / {pose_target}  frames",
                        fh // 2 + 68, 0.5, DIM, 1)

            # Bottom labels
            cv2.putText(frame, f"Pose {pose_idx + 1} of {len(POSES)}", (20, fh - 22),
                        FONT, 0.5, DIM, 1, cv2.LINE_AA)
            cv2.putText(frame, f"Enrolling: {person_name}", (fw - 260, fh - 22),
                        FONT, 0.5, CYAN, 1, cv2.LINE_AA)

            # Auto-capture when face detected (throttled to ~12fps)
            now = time.time()
            if face_found and captured < pose_target and (now - last_capture) >= 0.08:
                fname = save_dir / f"{person_name}_{pose_idx:02d}_{captured:03d}.jpg"
                cv2.imwrite(str(fname), raw)   # save clean frame, not the one with overlay
                captured     += 1
                last_capture  = now

            # Done with this pose?
            if captured >= pose_target:
                pose_idx += 1
                captured  = 0
                if pose_idx >= len(POSES):
                    state = DONE
                else:
                    # Brief countdown before next pose
                    countdown_start = time.time()
                    state = COUNTDOWN

        # ── DONE ──────────────────────────────────────────────────────────────
        elif state == DONE:
            text_center(frame, f"{person_name.upper()} enrolled.", fh // 2 - 40, 1.1, GREEN, 2)
            text_center(frame, f"{TOTAL_FRAMES} frames saved to known_faces/{person_name}/",
                        fh // 2 + 20, 0.52, DIM, 1)
            text_center(frame, "SPACE  enroll another person     ESC  quit",
                        fh // 2 + 70, 0.5, DIM, 1)

        # ── Key handling ──────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF

        if key == 27:  # ESC
            break

        elif state == IDLE and key == 32:
            state       = NAME
            person_name = ""

        elif state == NAME:
            if key == 13:  # ENTER
                n = person_name.strip().lower()
                if n:
                    person_name      = n
                    save_dir         = FACES_DIR / person_name
                    save_dir.mkdir(parents=True, exist_ok=True)
                    pose_idx         = 0
                    captured         = 0
                    countdown_start  = time.time()
                    state            = COUNTDOWN
            elif key == 8:  # BACKSPACE
                person_name = person_name[:-1]
            elif 32 <= key <= 126:
                person_name += chr(key)

        elif state == DONE and key == 32:
            state       = IDLE
            person_name = ""
            pose_idx    = 0
            captured    = 0

        cv2.imshow("Echo Face Enrollment", frame)

    cap.release()
    cv2.destroyAllWindows()
    print(f"\nDone. Frames saved to: {FACES_DIR}")
    print("Restart echo_server.py / echo_identify.py to reload recognition.")


if __name__ == "__main__":
    run()
