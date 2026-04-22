import lgpio
import time
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

LEFT_IN3  = 17
LEFT_IN4  = 24
RIGHT_IN3 = 25
RIGHT_IN4 = 5

PINS = [LEFT_IN3, LEFT_IN4, RIGHT_IN3, RIGHT_IN4]

h = lgpio.gpiochip_open(0)
for pin in PINS:
    lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, pin, 0)

drive_lock = threading.Lock()

def stop():
    for pin in PINS:
        lgpio.gpio_write(h, pin, 0)

def forward():
    lgpio.gpio_write(h, LEFT_IN3, 1)
    lgpio.gpio_write(h, LEFT_IN4, 0)
    lgpio.gpio_write(h, RIGHT_IN3, 1)
    lgpio.gpio_write(h, RIGHT_IN4, 0)

def backward():
    lgpio.gpio_write(h, LEFT_IN3, 0)
    lgpio.gpio_write(h, LEFT_IN4, 1)
    lgpio.gpio_write(h, RIGHT_IN3, 0)
    lgpio.gpio_write(h, RIGHT_IN4, 1)

def turn_left():
    lgpio.gpio_write(h, LEFT_IN3, 0)
    lgpio.gpio_write(h, LEFT_IN4, 1)
    lgpio.gpio_write(h, RIGHT_IN3, 1)
    lgpio.gpio_write(h, RIGHT_IN4, 0)

def turn_right():
    lgpio.gpio_write(h, LEFT_IN3, 1)
    lgpio.gpio_write(h, LEFT_IN4, 0)
    lgpio.gpio_write(h, RIGHT_IN3, 0)
    lgpio.gpio_write(h, RIGHT_IN4, 1)

COMMANDS = {
    "forward":    forward,
    "backward":   backward,
    "back":       backward,
    "reverse":    backward,
    "left":       turn_left,
    "turn left":  turn_left,
    "right":      turn_right,
    "turn right": turn_right,
    "stop":       stop,
}

def run_drive(direction, duration):
    with drive_lock:
        action = COMMANDS.get(direction)
        if action:
            action()
            if direction != "stop":
                time.sleep(duration)
                stop()

@app.route("/drive", methods=["POST"])
def drive():
    data = request.get_json()
    direction = data.get("direction", "").lower().strip()
    duration = float(data.get("duration", 2))

    if direction not in COMMANDS:
        return jsonify({"error": f"Unknown direction: {direction}"}), 400

    t = threading.Thread(target=run_drive, args=(direction, duration))
    t.start()
    return jsonify({"ok": True, "direction": direction, "duration": duration})

@app.route("/stop", methods=["POST"])
def emergency_stop():
    stop()
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("Drive server running on port 5102")
    try:
        app.run(host="0.0.0.0", port=5102)
    finally:
        stop()
        lgpio.gpiochip_close(h)
