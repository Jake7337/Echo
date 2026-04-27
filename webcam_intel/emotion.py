"""
emotion.py
Emotion / expression detection for Echo's Webcam Intelligence Module.

Current state: stub returning neutral — honest about why.
DeepFace requires TensorFlow which conflicts with Python 3.14 packages.
This module is GPU-upgrade-ready — when RTX 5070 is back and a compatible
Python env is available, swap the stub for the deepface block below.

The interface stays identical either way — pipeline.py doesn't change.
"""


class EmotionDetector:
    def __init__(self):
        self._backend = self._load_backend()

    def _load_backend(self):
        # Try deepface first — will work once TF conflict is resolved
        try:
            from deepface import DeepFace
            print("[emotion] DeepFace loaded — real emotion detection active", flush=True)
            return "deepface"
        except Exception:
            pass

        print("[emotion] Running stub — upgrade path: resolve TF/Python 3.14 conflict, "
              "then deepface will auto-activate", flush=True)
        return "stub"

    def analyze(self, frame, face_bboxes: list) -> list:
        """
        Analyze emotion for each detected face.
        Returns list of {label, confidence} — parallel to face_bboxes.
        """
        if self._backend == "deepface":
            return self._analyze_deepface(frame, face_bboxes)
        return self._analyze_stub(face_bboxes)

    def _analyze_deepface(self, frame, face_bboxes: list) -> list:
        from deepface import DeepFace
        results = []
        for bbox in face_bboxes:
            x, y, w, h = bbox
            try:
                face_crop = frame[y:y+h, x:x+w]
                analysis  = DeepFace.analyze(
                    face_crop,
                    actions=["emotion"],
                    enforce_detection=False,
                    silent=True,
                )
                emotions = analysis[0]["emotion"] if isinstance(analysis, list) else analysis["emotion"]
                dominant = max(emotions, key=emotions.get)
                results.append({
                    "label":      dominant.lower(),
                    "confidence": round(emotions[dominant] / 100.0, 3),
                })
            except Exception as e:
                results.append({"label": "unknown", "confidence": 0.0})
        return results

    def _analyze_stub(self, face_bboxes: list) -> list:
        # Returns neutral for all faces — placeholder until GPU upgrade
        return [{"label": "neutral", "confidence": 0.0} for _ in face_bboxes]
