"""Device-side enrollment. A draft and one pending sample live only in memory."""
from __future__ import annotations

import shutil
import hashlib
from typing import TYPE_CHECKING

from ..config import Config

if TYPE_CHECKING:
    from ..controller import Controller

from ..audio.wavio import write_wav
from .classifier import PrototypeClassifier
from ..recognizer import Recognizer, profile_path


class EnrollmentService:
    def __init__(self, cfg: Config, controller: Controller) -> None:
        self.cfg, self.controller = cfg, controller
        self.rec = controller.recognizer or Recognizer(cfg)
        self.draft: PrototypeClassifier | None = None
        self.intent = None
        self.pending = None
        self.keep_audio = False

    def status(self) -> dict:
        root = profile_path(self.cfg).parent
        return {"active_profile": self.rec.profile_id, "ready": self.rec.ready,
                "profile_error": self.rec.profile_error,
                "profiles": sorted(p.name for p in root.iterdir() if p.is_dir() and
                                   (p / "metadata.json").exists()) if root.exists() else [],
                "enrolling": self.controller.enrollment_active,
                "profile_id": self.draft.profile_id if self.draft else None,
                "intent": self.intent, "counts": self.draft.counts() if self.draft else {},
                "calibration": self.draft.calibration if self.draft else self.rec.clf.calibration,
                "intents": [{"id": i.id, "label": i.label, "speak": i.speak} for i in self.cfg.intents],
                "has_mic": self.controller.capture is not None, "target_samples": 5}

    def start(self, profile_id: str, keep_audio: bool = False) -> dict:
        path = profile_path(self.cfg, profile_id)
        if self.controller.state != "IDLE":
            raise ValueError("confirm or cancel the pending interaction before enrollment")
        draft = PrototypeClassifier.load(path) if path.exists() else self.rec.new_classifier()
        if path.exists() and draft.profile_id != profile_id:
            raise ValueError("profile ID does not match its directory")
        draft.profile_id = profile_id
        self.draft, self.intent, self.pending = draft, None, None
        self.keep_audio = keep_audio
        self.controller.enrollment_active = True
        self.controller._publish()
        return self.status()

    def select(self, intent: str) -> dict:
        self._require_draft()
        if self.cfg.intent(intent) is None:
            raise ValueError("unknown intent")
        self.intent, self.pending = intent, None
        return self.status()

    def _require_draft(self) -> None:
        if self.draft is None or not self.controller.enrollment_active:
            raise ValueError("start enrollment first")

    def capture(self, manual: bool = True, seconds: float = 3., test: bool = False) -> dict:
        self._require_draft()
        if not test and self.intent is None:
            raise ValueError("select an intent first")
        self.pending = None
        cap = self.controller.capture
        if cap is None:
            raise RuntimeError("no device microphone; attach a microphone and restart Sonara")
        self.controller.speaker.wait_idle()
        cap.flush()
        audio = cap.record_manual(seconds) if manual else cap.record_utterance(wait_s=4.)
        if audio is None:
            raise ValueError("no speech detected; try manual boundaries")
        speech, quality = self.rec.prepare(audio, manual)
        # Draft configuration may differ from the active profile.
        from .embedder import MFCCEmbedder
        seq = MFCCEmbedder(self.draft.feature_config)(speech)
        if test:
            result = self.draft.predict(seq)
            return {"quality": quality, "prediction": result.to_dict()}
        self.pending = (seq, audio, quality)
        return {"quality": quality, "pending": True}

    def save_sample(self) -> dict:
        self._require_draft()
        if self.pending is None or self.intent is None:
            raise ValueError("record a valid sample first")
        seq, audio, _ = self.pending
        self.draft.add(self.intent, seq)
        if self.keep_audio:
            write_wav(profile_path(self.cfg, self.draft.profile_id) / "recordings" / self.intent /
                      f"{hashlib.sha256(seq.tobytes()).hexdigest()}.wav", audio, 16000)
        self.pending = None
        self._save()
        return self.status()

    def _save(self) -> None:
        self.draft.calibrate()
        self.draft.save(profile_path(self.cfg, self.draft.profile_id))
        if self.rec.profile_id == self.draft.profile_id:
            self.rec.reload(self.draft.profile_id)

    def remove(self, intent: str, index: int | None = None) -> dict:
        self._require_draft()
        recordings = profile_path(self.cfg, self.draft.profile_id) / "recordings" / intent
        if self.cfg.intent(intent) is None:
            raise ValueError("unknown intent")
        if index is None:
            self.draft.remove_label(intent)
            if recordings.exists():
                shutil.rmtree(recordings)
        else:
            positions = [i for i, label in enumerate(self.draft.labels) if label == intent]
            if not 0 <= index < len(positions):
                raise ValueError("sample index out of range")
            i = positions[index]
            raw = recordings / f"{hashlib.sha256(self.draft.seqs[i].tobytes()).hexdigest()}.wav"
            raw.unlink(missing_ok=True)
            del self.draft.labels[i]
            del self.draft.seqs[i]
        self.pending = None
        self._save()
        return self.status()

    def calibrate(self) -> dict:
        self._require_draft()
        self._save()
        return self.status()

    def load(self, profile_id: str) -> dict:
        self.rec.reload(profile_id)
        if self.controller.recognizer is None:
            self.controller.recognizer = self.rec
        return self.status()

    def finish(self) -> dict:
        self._require_draft()
        if not self.draft.seqs:
            raise ValueError("save at least one recording before finishing")
        self._save()
        self.load(self.draft.profile_id)
        self.controller.enrollment_active = False
        self.draft, self.pending, self.intent = None, None, None
        self.controller._publish()
        return self.status()

    def cancel(self) -> dict:
        self.controller.enrollment_active = False
        self.draft, self.pending, self.intent = None, None, None
        self.controller._publish()
        return self.status()

    def delete(self, profile_id: str) -> dict:
        path = profile_path(self.cfg, profile_id)
        if self.draft and self.draft.profile_id == profile_id:
            self.cancel()
        if path.exists():
            shutil.rmtree(path)
        if self.rec.profile_id == profile_id:
            self.rec.reload()
        return self.status()
