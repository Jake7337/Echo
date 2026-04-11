"""
face.py
Echo's animated face — tkinter window with blinking eyes and talking mouth.
Run alongside echo.py. States: idle, listening, thinking, talking.
"""

import tkinter as tk
import threading
import time
import random
import sys

# ── Config ─────────────────────────────────────────────────────────────────────

WIDTH   = 480
HEIGHT  = 360
BG      = "#0a0a0a"
EYE_COLOR    = "#00ccff"
MOUTH_COLOR  = "#00ccff"
GLOW_COLOR   = "#003344"

# Eye positions
LEFT_EYE_X  = WIDTH // 2 - 90
RIGHT_EYE_X = WIDTH // 2 + 90
EYE_Y       = HEIGHT // 2 - 30
EYE_W       = 60
EYE_H       = 60

# Mouth
MOUTH_X = WIDTH // 2
MOUTH_Y = HEIGHT // 2 + 70
MOUTH_W = 100


# ── Face State ─────────────────────────────────────────────────────────────────

class FaceState:
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    TALKING   = "talking"


class EchoFace:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Echo")
        self.root.geometry(f"{WIDTH}x{HEIGHT}")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                bg=BG, highlightthickness=0)
        self.canvas.pack()

        self.state      = FaceState.IDLE
        self.blink_open = True
        self.mouth_open = 0   # 0-10, how open the mouth is
        self.talk_tick  = 0

        self._draw()
        self._schedule_blink()
        self._animate_loop()

    # ── State control (call from outside) ─────────────────────────────────────

    def set_state(self, state: str):
        self.state = state

    # ── Drawing ────────────────────────────────────────────────────────────────

    def _draw(self):
        self.canvas.delete("all")
        self._draw_eyes()
        self._draw_mouth()
        self._draw_label()

    def _draw_eyes(self):
        blink_h = EYE_H if self.blink_open else 4

        for x in (LEFT_EYE_X, RIGHT_EYE_X):
            # Glow
            self.canvas.create_oval(
                x - EYE_W//2 - 8, EYE_Y - blink_h//2 - 8,
                x + EYE_W//2 + 8, EYE_Y + blink_h//2 + 8,
                fill=GLOW_COLOR, outline=""
            )
            # Eye
            self.canvas.create_oval(
                x - EYE_W//2, EYE_Y - blink_h//2,
                x + EYE_W//2, EYE_Y + blink_h//2,
                fill=EYE_COLOR, outline=""
            )
            # Pupil
            if self.blink_open:
                self.canvas.create_oval(
                    x - 12, EYE_Y - 12,
                    x + 12, EYE_Y + 12,
                    fill=BG, outline=""
                )

    def _draw_mouth(self):
        mo = self.mouth_open
        if mo == 0:
            # Flat line
            self.canvas.create_line(
                MOUTH_X - MOUTH_W//2, MOUTH_Y,
                MOUTH_X + MOUTH_W//2, MOUTH_Y,
                fill=MOUTH_COLOR, width=3
            )
        else:
            h = max(4, mo * 4)
            self.canvas.create_oval(
                MOUTH_X - MOUTH_W//2, MOUTH_Y - h//2,
                MOUTH_X + MOUTH_W//2, MOUTH_Y + h//2,
                outline=MOUTH_COLOR, width=3, fill=BG
            )

    def _draw_label(self):
        labels = {
            FaceState.IDLE:      "",
            FaceState.LISTENING: "listening...",
            FaceState.THINKING:  "thinking...",
            FaceState.TALKING:   "",
        }
        text = labels.get(self.state, "")
        if text:
            self.canvas.create_text(
                WIDTH // 2, HEIGHT - 30,
                text=text, fill="#336677",
                font=("Courier", 12)
            )

    # ── Blink ──────────────────────────────────────────────────────────────────

    def _schedule_blink(self):
        delay = random.randint(2000, 5000)
        self.root.after(delay, self._do_blink)

    def _do_blink(self):
        self.blink_open = False
        self._draw()
        self.root.after(120, self._end_blink)

    def _end_blink(self):
        self.blink_open = True
        self._draw()
        self._schedule_blink()

    # ── Animation loop ─────────────────────────────────────────────────────────

    def _animate_loop(self):
        if self.state == FaceState.TALKING:
            self.talk_tick += 1
            self.mouth_open = 5 + int(4 * abs(
                (self.talk_tick % 6) - 3
            ) // 3)
        elif self.state == FaceState.LISTENING:
            self.mouth_open = 1
        else:
            self.mouth_open = 0

        self._draw()
        self.root.after(80, self._animate_loop)

    def run(self):
        self.root.mainloop()


# ── Run standalone or import ────────────────────────────────────────────────────

_face: EchoFace = None

def start_face():
    """Launch face in its own thread."""
    global _face
    def _run():
        global _face
        _face = EchoFace()
        _face.run()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.5)  # let it initialize

def set_state(state: str):
    if _face:
        _face.set_state(state)

def listening():  set_state(FaceState.LISTENING)
def thinking():   set_state(FaceState.THINKING)
def talking():    set_state(FaceState.TALKING)
def idle():       set_state(FaceState.IDLE)


def start_udp_listener(face_instance: EchoFace, port: int = 5005):
    """Listen for state updates from the Pi over UDP."""
    import socket
    _pending = []

    def _listen():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        while True:
            try:
                data, _ = sock.recvfrom(64)
                state = data.decode().strip()
                _pending.append(state)
            except Exception:
                pass

    def _poll():
        while _pending:
            face_instance.set_state(_pending.pop(0))
        face_instance.root.after(50, _poll)

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    face_instance.root.after(50, _poll)


if __name__ == "__main__":
    # Network mode — face listens for UDP state from Pi
    face = EchoFace()

    def demo():
        states = [
            (FaceState.IDLE,      2000),
            (FaceState.LISTENING, 2000),
            (FaceState.THINKING,  2000),
            (FaceState.TALKING,   3000),
            (FaceState.IDLE,      2000),
        ]
        def step(i=0):
            state, delay = states[i % len(states)]
            face.set_state(state)
            face.root.after(delay, step, i + 1)
        step()

    start_udp_listener(face, port=5005)
    print("Face listening for Pi state on UDP port 5005...")
    face.run()
