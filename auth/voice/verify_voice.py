import numpy as np
import sounddevice as sd
import torch
from scipy.io.wavfile import write, read
import os

if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = os.path.join(os.path.expanduser("~"), ".cache", "huggingface")

# ── Compatibility shim ──────────────────────────────────────
# speechbrain 0.5.x used `speechbrain.pretrained`
# speechbrain 1.x moved it to `speechbrain.inference`
# Also patch huggingface_hub to strip deprecated `use_auth_token`
import huggingface_hub

_original_hf_download = huggingface_hub.hf_hub_download
def _patched_hf_download(*args, **kwargs):
    kwargs.pop("use_auth_token", None)
    return _original_hf_download(*args, **kwargs)
huggingface_hub.hf_hub_download = _patched_hf_download

if hasattr(huggingface_hub, "snapshot_download"):
    _original_snapshot = huggingface_hub.snapshot_download
    def _patched_snapshot(*args, **kwargs):
        kwargs.pop("use_auth_token", None)
        return _original_snapshot(*args, **kwargs)
    huggingface_hub.snapshot_download = _patched_snapshot

# Try speechbrain 1.x API first, fall back to 0.5.x
try:
    from speechbrain.inference.classifiers import EncoderClassifier
except (ImportError, Exception):
    try:
        from speechbrain.pretrained import EncoderClassifier
    except (ImportError, Exception):
        raise ImportError(
            "Could not import EncoderClassifier from speechbrain. "
            "Install a compatible version: pip install speechbrain>=1.0"
        )
# ─────────────────────────────────────────────────────────────
from .vad import remove_silence

SAMPLE_RATE = 16000
DURATION = 5
TEMP_FILE = "temp_verify.wav"
THRESHOLD = 0.35   # Lowered from 0.50 — live scores observed: 0.37-0.49

import sys

# On Windows, SpeechBrain's default SYMLINK strategy requires admin privileges.
# Use COPY strategy instead.
_from_hparams_kwargs = {}
if sys.platform == "win32":
    try:
        from speechbrain.utils.fetching import LocalStrategy
        _from_hparams_kwargs["local_strategy"] = LocalStrategy.COPY
    except ImportError:
        pass

classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/spkrec-ecapa-voxceleb",
    run_opts={"device": "cpu"},
    **_from_hparams_kwargs,
)
owner_embeddings = np.load("data/voice_profile/owner_embeddings.npy")


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def verify_voice():

    print("Verifying speaker...")

    audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()

    write(TEMP_FILE, SAMPLE_RATE, audio)

    fs, signal = read(TEMP_FILE)
    
    signal = torch.tensor(signal, dtype=torch.float32).unsqueeze(0) / 32768.0

    audio_np = signal.squeeze().numpy()

    audio_np = remove_silence(audio_np)

    signal = torch.tensor(audio_np).unsqueeze(0)

    embedding = classifier.encode_batch(signal).squeeze().detach().numpy()

    embedding = embedding / np.linalg.norm(embedding)

    best_score = 0

    for owner_emb in owner_embeddings:

        score = cosine_similarity(embedding, owner_emb)

        best_score = max(best_score, score)

    print("Best similarity:", best_score)

    return best_score > THRESHOLD