import gpiod
from gpiod.line import Direction, Value
import time

print("Claiming GPIO 22 HIGH, GPIO 23 LOW for 10 seconds...")

with gpiod.request_lines(
    "/dev/gpiochip0",
    consumer="test",
    config={
        22: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
        23: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
    }
) as req:
    print("Pins set. Right motors should spin now.")
    print("Measuring with multimeter: put red on pin 15 (GPIO 22), black on pin 6 (GND)")
    time.sleep(10)
    print("Done.")
