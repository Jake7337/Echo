import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(17, GPIO.OUT)

print("Setting GPIO 17 HIGH for 10 seconds...")
GPIO.output(17, GPIO.HIGH)
print("GPIO 17 is HIGH now — watch bench supply amps")
time.sleep(10)

print("Setting GPIO 17 LOW")
GPIO.output(17, GPIO.LOW)
GPIO.cleanup()
print("Done")
