"""
motor_test.py
Echo chassis motor test — run this on the Pi to verify wiring.
Tests each direction one at a time. Press Enter between each move.
"""

import RPi.GPIO as GPIO
import time

# ── Pin config ─────────────────────────────────────────────────────────────────
ENA = 12   # Board 1 Left  — PWM enable
IN1 = 17   # Board 1 Left  — direction
IN2 = 27   # Board 1 Left  — direction

ENB = 13   # Board 2 Right — PWM enable
IN3 = 22   # Board 2 Right — direction
IN4 = 23   # Board 2 Right — direction

SPEED = 35  # % duty cycle — safe for 3-6V motors on 6V battery pack

# ── Setup ──────────────────────────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup([ENA, IN1, IN2, ENB, IN3, IN4], GPIO.OUT)

pwm_left  = GPIO.PWM(ENA, 1000)
pwm_right = GPIO.PWM(ENB, 1000)
pwm_left.start(0)
pwm_right.start(0)


# ── Motor commands ─────────────────────────────────────────────────────────────
def stop():
    GPIO.output([IN1, IN2, IN3, IN4], GPIO.LOW)
    pwm_left.ChangeDutyCycle(0)
    pwm_right.ChangeDutyCycle(0)

def forward():
    GPIO.output(IN1, GPIO.HIGH); GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.HIGH); GPIO.output(IN4, GPIO.LOW)
    pwm_left.ChangeDutyCycle(SPEED)
    pwm_right.ChangeDutyCycle(SPEED)

def backward():
    GPIO.output(IN1, GPIO.LOW);  GPIO.output(IN2, GPIO.HIGH)
    GPIO.output(IN3, GPIO.LOW);  GPIO.output(IN4, GPIO.HIGH)
    pwm_left.ChangeDutyCycle(SPEED)
    pwm_right.ChangeDutyCycle(SPEED)

def turn_left():
    GPIO.output(IN1, GPIO.LOW);  GPIO.output(IN2, GPIO.HIGH)
    GPIO.output(IN3, GPIO.HIGH); GPIO.output(IN4, GPIO.LOW)
    pwm_left.ChangeDutyCycle(SPEED)
    pwm_right.ChangeDutyCycle(SPEED)

def turn_right():
    GPIO.output(IN1, GPIO.HIGH); GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.LOW);  GPIO.output(IN4, GPIO.HIGH)
    pwm_left.ChangeDutyCycle(SPEED)
    pwm_right.ChangeDutyCycle(SPEED)


# ── Test sequence ──────────────────────────────────────────────────────────────
def run_test(label, fn):
    input(f"\nReady to test: {label} — press Enter...")
    print(f"  >> {label} for 2 seconds")
    fn()
    time.sleep(2)
    stop()
    print("  >> Stopped")

try:
    print("\n=== ECHO MOTOR TEST ===")
    print(f"Speed: {SPEED}% duty cycle")
    print("Make sure Echo is on a surface where she can move safely.")

    run_test("FORWARD",   forward)
    run_test("BACKWARD",  backward)
    run_test("TURN LEFT", turn_left)
    run_test("TURN RIGHT",turn_right)

    print("\nAll tests complete. Echo moves.")

except KeyboardInterrupt:
    print("\nTest cancelled.")

finally:
    stop()
    pwm_left.stop()
    pwm_right.stop()
    GPIO.cleanup()
