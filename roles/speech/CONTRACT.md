# speech CONTRACT: what device may rely on

Change only with a `CONTRACT` post to `device`.

```python
from sonara.recognizer import Recognizer
rec = Recognizer(cfg, backend=None)        # backend from config: "oww" | "mfcc"
rec.ready -> bool                          # a profile is enrolled
rec.recognize(audio: np.ndarray[float32, 16 kHz mono, -1..1]) -> Prediction | None
    # None = no usable speech in the clip

from sonara.models.classifier import Prediction
p.intent   -> str | None      # None = rejected (below threshold or ambiguous); device must not dispatch
p.accepted -> bool
p.best     -> str             # best guess even if rejected (logs/metrics only, never shown as a result)
p.score    -> float 0..1      # display score, NOT a calibrated probability
p.distance, p.margin, p.threshold -> float

from sonara.audio.capture import AudioCapture
cap.flush(); cap.record_utterance(wait_s) -> np.ndarray | None; cap.close()

from sonara.tts import Speaker
spk.say(key) / spk.say_now(key) / spk.wait_idle(timeout)
    # key = intent id ("WATER") or prompt name ("acknowledged") from config/intents.toml
```

Intent IDs come from `config/intents.toml` (owned by ui). Profiles are stored as
`data/profiles/<bed_id>_<backend>.{npz,json}` (embeddings only).
