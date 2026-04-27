import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup([17, 27], GPIO.OUT)

print("Setting IN1 HIGH, IN2 LOW for 3 seconds...")
GPIO.output(17, GPIO.HIGH)
GPIO.output(27, GPIO.LOW)
time.sleep(3)
GPIO.output(17, GPIO.LOW)
GPIO.cleanup()
print("Done")
