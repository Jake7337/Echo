"""
lidar.py
3iRobotix Delta-SC-02 LiDAR interface for Echo chassis.

Reads 360° scan data from /dev/serial0 at 115200 baud.
Provides obstacle detection and distance readings for drive integration.

Wiring (after voltage divider on TX line):
  Pi pin 2  (5V)  → LiDAR red   (sensor VCC)
  Pi pin 4  (5V)  → LiDAR purple (motor)
  Pi pin 6  (GND) → LiDAR black #1 (sensor GND)
  Pi pin 14 (GND) → LiDAR black #2 (motor GND)
  LiDAR white (TX) → [10kΩ + 20kΩ divider] → Pi pin 10 (UART RX)
"""

import serial
import struct
import time
import threading
from collections import defaultdict

SERIAL_PORT = "/dev/serial0"
BAUD_RATE   = 115200

# Obstacle threshold in mm — closer than this = blocked
OBSTACLE_MM = 500  # 50cm

# Sectors for obstacle detection (degrees)
SECTORS = {
    "front":  (-30, 30),
    "left":   (60, 120),
    "right":  (-120, -60),
    "rear":   (150, 180),   # also catches -180 to -150
}


# ── Packet parsing ─────────────────────────────────────────────────────────────
# Delta series protocol:
#   Header: 0xAA 0x55
#   Packet type, length, then angle/distance pairs

def _parse_packet(data: bytes) -> list:
    """
    Parse one Delta-series LiDAR packet.
    Returns list of (angle_deg, distance_mm) tuples.
    """
    points = []
    i = 0
    while i < len(data) - 1:
        # Scan for header
        if data[i] != 0xAA or data[i + 1] != 0x55:
            i += 1
            continue

        if i + 6 > len(data):
            break

        pkt_len   = data[i + 2]
        pkt_type  = data[i + 3]

        if pkt_type != 0xAD:        # 0xAD = measurement packet
            i += 4 + pkt_len
            continue

        if i + 4 + pkt_len > len(data):
            break

        payload = data[i + 4: i + 4 + pkt_len]

        if len(payload) < 6:
            i += 4 + pkt_len
            continue

        start_angle = struct.unpack_from("<H", payload, 0)[0] / 100.0  # degrees
        sample_count = payload[2]

        for s in range(sample_count):
            offset = 3 + s * 3
            if offset + 3 > len(payload):
                break
            quality   = payload[offset]
            dist_raw  = struct.unpack_from("<H", payload, offset + 1)[0]
            dist_mm   = dist_raw * 0.25

            angle = (start_angle + (s * 360.0 / sample_count)) % 360
            # Normalize to -180..180
            if angle > 180:
                angle -= 360

            if quality > 0 and dist_mm > 0:
                points.append((angle, dist_mm))

        i += 4 + pkt_len

    return points


# ── LiDAR reader ───────────────────────────────────────────────────────────────

class LiDAR:
    """
    Background thread that continuously reads and parses LiDAR data.
    Query scan() for the latest 360° snapshot.
    Query obstacles() to check which directions are blocked.
    """

    def __init__(self, port=SERIAL_PORT, baud=BAUD_RATE):
        self._port    = port
        self._baud    = baud
        self._lock    = threading.Lock()
        self._scan    = {}          # angle → distance_mm (latest full scan)
        self._running = False
        self._thread  = None

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[lidar] Started on {self._port} @ {self._baud} baud", flush=True)

    def stop(self):
        self._running = False

    def scan(self) -> dict:
        """Return copy of latest scan: {angle: distance_mm}"""
        with self._lock:
            return dict(self._scan)

    def distance_at(self, angle: float, window: float = 10.0) -> float:
        """
        Return minimum distance (mm) within ±window degrees of angle.
        Returns 0 if no reading available.
        """
        with self._lock:
            readings = [
                d for a, d in self._scan.items()
                if abs(a - angle) <= window or abs(abs(a - angle) - 360) <= window
            ]
        return min(readings) if readings else 0

    def obstacles(self, threshold_mm: int = OBSTACLE_MM) -> dict:
        """
        Returns dict of sector → closest distance (mm).
        Sector is considered blocked if closest < threshold_mm.
        """
        result = {}
        current = self.scan()
        for sector, (start, end) in SECTORS.items():
            readings = [
                d for a, d in current.items()
                if start <= a <= end
            ]
            result[sector] = min(readings) if readings else None
        return result

    def is_blocked(self, direction: str, threshold_mm: int = OBSTACLE_MM) -> bool:
        """Check if a specific direction is blocked."""
        obs = self.obstacles(threshold_mm)
        dist = obs.get(direction)
        if dist is None:
            return False
        return dist < threshold_mm

    def _run(self):
        try:
            ser = serial.Serial(self._port, self._baud, timeout=1)
        except Exception as e:
            print(f"[lidar] Failed to open port: {e}", flush=True)
            return

        buf = b""
        while self._running:
            try:
                chunk = ser.read(256)
                if not chunk:
                    continue
                buf += chunk
                if len(buf) > 4096:
                    buf = buf[-2048:]   # prevent runaway buffer

                points = _parse_packet(buf)
                if points:
                    with self._lock:
                        for angle, dist in points:
                            self._scan[round(angle, 1)] = dist
                    buf = b""           # consumed — reset for next frame

            except Exception as e:
                print(f"[lidar] Read error: {e}", flush=True)
                time.sleep(0.1)

        ser.close()


# ── Raw test mode ──────────────────────────────────────────────────────────────

def test_raw():
    """
    Dump raw bytes from the LiDAR to confirm data is flowing.
    Run this first after wiring to verify the connection is alive.
    """
    print(f"Opening {SERIAL_PORT} at {BAUD_RATE} baud...")
    print("Waiting for data — Ctrl+C to stop.\n")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
        for _ in range(20):
            data = ser.read(64)
            if data:
                print(f"  {data.hex(' ')}")
            else:
                print("  (no data)")
        ser.close()
    except serial.SerialException as e:
        print(f"Error: {e}")
        print("Check wiring and that UART is enabled (raspi-config → Interface Options → Serial Port)")


def test_scan():
    """
    Print live obstacle readings. Run after test_raw confirms data is flowing.
    """
    lidar = LiDAR()
    lidar.start()
    time.sleep(2)   # let it fill up a scan

    print("Live obstacle readings — Ctrl+C to stop.\n")
    try:
        while True:
            obs = lidar.obstacles()
            parts = []
            for sector, dist in obs.items():
                if dist is None:
                    parts.append(f"{sector}: --")
                elif dist < OBSTACLE_MM:
                    parts.append(f"{sector}: {dist:.0f}mm ⚠️")
                else:
                    parts.append(f"{sector}: {dist:.0f}mm OK")
            print("  " + "    ".join(parts))
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped.")
        lidar.stop()


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "raw"
    if mode == "scan":
        test_scan()
    else:
        test_raw()
