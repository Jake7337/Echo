"""
motor_test.py
Echo chassis motor test — gpiod version for Debian Trixie.
Board 1 Left:  IN3=GPIO17(pin11), IN4=GPIO27(pin13)
Board 2 Right: IN3=GPIO22(pin15), IN4=GPIO23(pin16)
ENA/ENB jumpered on both boards (always enabled).
"""

import gpiod
from gpiod.line import Direction, Value
import time

CHIP = "/dev/gpiochip0"

# Pin assignments
L_IN3 = 17   # Board 1 Left forward
L_IN4 = 27   # Board 1 Left reverse
R_IN3 = 22   # Board 2 Right forward
R_IN4 = 23   # Board 2 Right reverse

ON  = Value.ACTIVE
OFF = Value.INACTIVE

def run_test(label, vals, request):
    input(f"\nReady: {label} — press Enter...")
    for pin, val in vals.items():
        request.set_value(pin, val)
    print(f"  >> {label} running...")
    input("Press Enter to stop...")
    for pin in vals:
        request.set_value(pin, OFF)
    print("  >> Stopped")

print("\n=== ECHO MOTOR TEST (gpiod) ===")
print("Bench supply on. Echo on a safe surface.")

with gpiod.request_lines(
    CHIP,
    consumer="echo-motor-test",
    config={
        (L_IN3, L_IN4, R_IN3, R_IN4): gpiod.LineSettings(
            direction=Direction.OUTPUT,
            output_value=OFF,
        )
    },
) as req:

    run_test("LEFT FORWARD",  {L_IN3: ON,  L_IN4: OFF}, req)
    run_test("LEFT BACKWARD", {L_IN3: OFF, L_IN4: ON},  req)
    run_test("RIGHT FORWARD", {R_IN3: ON,  R_IN4: OFF}, req)
    run_test("RIGHT BACKWARD",{R_IN3: OFF, R_IN4: ON},  req)
    run_test("FORWARD (both)",{L_IN3: ON,  L_IN4: OFF, R_IN3: ON,  R_IN4: OFF}, req)
    run_test("BACKWARD(both)",{L_IN3: OFF, L_IN4: ON,  R_IN3: OFF, R_IN4: ON},  req)
    run_test("TURN LEFT",     {L_IN3: OFF, L_IN4: ON,  R_IN3: ON,  R_IN4: OFF}, req)
    run_test("TURN RIGHT",    {L_IN3: ON,  L_IN4: OFF, R_IN3: OFF, R_IN4: ON},  req)

print("\nAll tests complete.")
