"""
voice_identify.py
Echo's voice identification system.
Extracts MFCC features from audio and compares against stored voice profiles.

Setup:
  pip install python_speech_features numpy
  python voice_enroll.py jake   (run once per person)

Profiles stored in voice_profiles/ — one .npy file per person.
"""

import os
import io
import wave
import numpy as np

BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
VOICE_PROFILES_DIR  = os.path.join(BASE_DIR, "voice_profiles")
THRESHOLD           = 0.18   # cosine distance — lower = stricter. Tune if needed.

# ── Feature extraction ────────────────────────────────────────────────────────

def extract_features(audio_data) -> np.ndarray | None:
    """Extract mean MFCC features from a SpeechRecognition AudioData object."""
    try:
        from python_speech_features import mfcc
        wav_bytes = audio_data.get_wav_data()
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            framerate = wf.getframerate()
            frames    = wf.readframes(wf.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
        if len(samples) < framerate * 0.5:   # less than 0.5s — too short
            return None
        features = mfcc(samples, samplerate=framerate, numcep=13, nfilt=26, nfft=512)
        return np.mean(features, axis=0)
    except Exception as e:
        print(f"[voice_id] Feature extraction failed: {e}", flush=True)
        return None


# ── Profile management ────────────────────────────────────────────────────────

def load_profiles() -> dict:
    """Load all voice profiles from voice_profiles/. Returns {name: features}."""
    profiles = {}
    if not os.path.exists(VOICE_PROFILES_DIR):
        return profiles
    for fname in sorted(os.listdir(VOICE_PROFILES_DIR)):
        if fname.endswith(".npy"):
            name = fname[:-4]
            try:
                profiles[name] = np.load(os.path.join(VOICE_PROFILES_DIR, fname))
                print(f"[voice_id] Loaded profile: {name}", flush=True)
            except Exception as e:
                print(f"[voice_id] Could not load {fname}: {e}", flush=True)
    return profiles


def save_profile(name: str, samples: list) -> bool:
    """
    Save a voice profile from a list of AudioData samples.
    Averages MFCC features across all samples.
    Returns True on success.
    """
    os.makedirs(VOICE_PROFILES_DIR, exist_ok=True)
    all_features = []
    for audio_data in samples:
        features = extract_features(audio_data)
        if features is not None:
            all_features.append(features)
    if not all_features:
        print(f"[voice_id] No usable samples for {name}.", flush=True)
        return False
    profile = np.mean(all_features, axis=0)
    path = os.path.join(VOICE_PROFILES_DIR, f"{name}.npy")
    np.save(path, profile)
    print(f"[voice_id] Profile saved: {path} ({len(all_features)} samples)", flush=True)
    return True


# ── Identification ────────────────────────────────────────────────────────────

# Cache profiles in memory so we don't hit disk on every call
_profiles: dict = {}
_profiles_loaded: bool = False

def _get_profiles() -> dict:
    global _profiles, _profiles_loaded
    if not _profiles_loaded:
        _profiles = load_profiles()
        _profiles_loaded = True
    return _profiles

def identify_voice(audio_data) -> str:
    """
    Identify the speaker from a SpeechRecognition AudioData object.
    Returns a name string or 'unknown'.
    """
    profiles = _get_profiles()
    if not profiles:
        return "unknown"

    features = extract_features(audio_data)
    if features is None:
        return "unknown"

    best_name = "unknown"
    best_dist = float("inf")

    for name, profile in profiles.items():
        norm = np.linalg.norm(features) * np.linalg.norm(profile)
        if norm == 0:
            continue
        cosine_dist = 1.0 - float(np.dot(features, profile)) / norm
        print(f"[voice_id] {name}: distance={cosine_dist:.3f}", flush=True)
        if cosine_dist < best_dist:
            best_dist  = cosine_dist
            best_name  = name

    if best_dist < THRESHOLD:
        print(f"[voice_id] Identified: {best_name} (dist={best_dist:.3f})", flush=True)
        return best_name

    print(f"[voice_id] Unknown speaker (best dist={best_dist:.3f}, threshold={THRESHOLD})", flush=True)
    return "unknown"
