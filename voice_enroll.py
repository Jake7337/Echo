"""
voice_enroll.py
Enroll a person's voice profile for Echo's speaker identification.

Usage:
  python voice_enroll.py jake
  python voice_enroll.py judy

Records 5 voice samples, extracts MFCC features, saves to voice_profiles/name.npy
Run once per person. Re-run to update an existing profile.
"""

import sys
import time
import speech_recognition as sr
from voice_identify import save_profile

SAMPLES_NEEDED = 5

def enroll(name: str):
    print(f"\nEnrolling voice profile for: {name}")
    print(f"Will record {SAMPLES_NEEDED} samples.")
    print("Speak naturally for a few seconds each time.\n")

    r = sr.Recognizer()
    r.energy_threshold  = 200
    r.pause_threshold   = 1.0

    mic_index = None
    for i, mic_name in enumerate(sr.Microphone.list_microphone_names()):
        if "fifine" in mic_name.lower() or "usb" in mic_name.lower():
            mic_index = i
            break

    samples = []
    attempt = 0

    while len(samples) < SAMPLES_NEEDED:
        attempt += 1
        print(f"Sample {len(samples)+1}/{SAMPLES_NEEDED} — speak now...")
        try:
            with sr.Microphone(device_index=mic_index) as source:
                r.adjust_for_ambient_noise(source, duration=0.3)
                audio = r.listen(source, timeout=8, phrase_time_limit=10)
            samples.append(audio)
            print(f"  Got it.")
            time.sleep(0.5)
        except sr.WaitTimeoutError:
            print(f"  Timed out — didn't hear anything. Try again.")
        except Exception as e:
            print(f"  Error: {e}")
        if attempt > SAMPLES_NEEDED * 3:
            print("Too many failures. Check your microphone.")
            sys.exit(1)

    print(f"\nProcessing {len(samples)} samples...")
    success = save_profile(name, samples)

    if success:
        print(f"\nDone. {name}'s voice profile saved.")
        print(f"Echo will recognize {name} by voice on next restart.")
    else:
        print(f"\nFailed to save profile for {name}. Try again with clearer audio.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python voice_enroll.py <name>")
        print("Example: python voice_enroll.py jake")
        sys.exit(1)
    enroll(sys.argv[1].lower())
