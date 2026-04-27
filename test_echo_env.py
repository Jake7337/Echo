"""
test_echo_env.py
Run with the EchoEnv venv to verify all webcam_intel dependencies load correctly.

    C:\EchoEnv\Scripts\python.exe test_echo_env.py
"""

import sys

print(f"\n  Python: {sys.version}")
print(f"  Executable: {sys.executable}\n")

results = []

def test(name, fn):
    try:
        fn()
        results.append((name, True, ""))
        print(f"  OK      {name}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  FAIL    {name}: {e}")

# ── Tests ─────────────────────────────────────────────────────────────────────

test("numpy",            lambda: __import__("numpy"))
test("cv2 (OpenCV)",     lambda: __import__("cv2"))
test("PIL (Pillow)",     lambda: __import__("PIL"))
test("flask",            lambda: __import__("flask"))
test("waitress",         lambda: __import__("waitress"))
test("requests",         lambda: __import__("requests"))

def test_dlib():
    import dlib
    # make sure native lib loads
    _ = dlib.get_frontal_face_detector()

def test_face_recognition():
    import face_recognition
    import numpy as np
    # create a blank image and run face_locations (should return [])
    blank = np.zeros((100, 100, 3), dtype="uint8")
    locs = face_recognition.face_locations(blank)
    assert isinstance(locs, list)

def test_mediapipe():
    import mediapipe as mp
    _ = mp.solutions.hands   # this is what fails on Python 3.14

test("dlib",             test_dlib)
test("face_recognition", test_face_recognition)
test("mediapipe",        test_mediapipe)
test("blinkpy",          lambda: __import__("blinkpy"))
test("discord",          lambda: __import__("discord"))

# ── Summary ───────────────────────────────────────────────────────────────────

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)

print(f"\n  {passed} passed / {failed} failed\n")

if failed:
    print("  Failed packages:")
    for name, ok, err in results:
        if not ok:
            print(f"    - {name}: {err}")
    print("\n  Fix: run setup_echo_venv.bat again, or pip install <package> manually.\n")
else:
    print("  All clear. Run webcam intel with: run_webcam.bat\n")
