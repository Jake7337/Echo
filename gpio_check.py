import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

pins = [17, 27, 22, 23]
for pin in pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)

print("All 4 pins set HIGH.")
print("Now touch a wire from Pi pin 1 (3.3V) to each breadboard row where")
print("your signal wires land. If a motor moves, that row is live.")
print("")

import time
time.sleep(10)

for pin in pins:
    GPIO.output(pin, GPIO.LOW)
GPIO.cleanup()
print("Done")
