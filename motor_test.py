import lgpio

LEFT_IN3  = 17
LEFT_IN4  = 24
RIGHT_IN3 = 25
RIGHT_IN4 = 5

PINS = [LEFT_IN3, LEFT_IN4, RIGHT_IN3, RIGHT_IN4]

h = lgpio.gpiochip_open(0)

for pin in PINS:
    lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, pin, 0)

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

print("Ready. f=forward b=backward s=stop q=quit")

try:
    while True:
        cmd = input("> ").strip().lower()
        if cmd == 'f':
            forward()
        elif cmd == 'b':
            backward()
        elif cmd == 's':
            stop()
        elif cmd == 'q':
            break
except KeyboardInterrupt:
    pass
finally:
    stop()
    lgpio.gpiochip_close(h)
