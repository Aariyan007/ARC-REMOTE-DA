import numpy as np
import torchaudio
import sounddevice as sd
import torch
from scipy.io.wavfile import write
from speechbrain.pretrained import EncoderClassifier
from auth.voice.vad import remove_silence

SAMPLE_RATE = 16000
DURATION = 5
TEMP_FILE = "temp_verify.wav"
THRESHOLD = 0.65

classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="models/ecapa"
)

owner_embeddings = np.load("data/voice_profile/owner_embeddings.npy")


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def verify_voice():

    print("Verifying speaker...")

    audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()

    write(TEMP_FILE, SAMPLE_RATE, audio)

    signal, fs = torchaudio.load(TEMP_FILE)

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