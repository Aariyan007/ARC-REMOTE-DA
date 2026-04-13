import numpy as np
import sounddevice as sd
import torch
from scipy.io.wavfile import write, read
import os
os.environ["HF_HOME"] = r"C:\hf_cache"

# ── Compatibility shim ──────────────────────────────────────
# speechbrain 0.5.16 uses deprecated `use_auth_token` kwarg
# which was removed in huggingface_hub >= 1.0.
# ONLY strip that kwarg — don't touch error handling, or it
# breaks transformers' graceful skip of optional files.
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

# Patch speechbrain's fetching to handle new HF error types
# (EntryNotFoundError instead of requests.HTTPError)
import speechbrain.pretrained.fetching as _sb_fetching
_original_fetch = _sb_fetching.fetch
def _patched_fetch(*args, **kwargs):
    kwargs.pop("use_auth_token", None)
    try:
        return _original_fetch(*args, **kwargs)
    except Exception as e:
        err_str = str(e)
        if "404" in err_str or "EntryNotFound" in type(e).__name__:
            raise ValueError(f"File not found on HF hub: {err_str}") from e
        raise
_sb_fetching.fetch = _patched_fetch
# ─────────────────────────────────────────────────────────────

from speechbrain.pretrained import EncoderClassifier
from .vad import remove_silence

SAMPLE_RATE = 16000
DURATION = 5
TEMP_FILE = "temp_verify.wav"
THRESHOLD = 0.50

classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/spkrec-ecapa-voxceleb",
    run_opts={"device": "cpu"}
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