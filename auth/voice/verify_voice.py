import numpy as np
import torchaudio
import sounddevice as sd
from scipy.io.wavfile import write
from speechbrain.pretrained import EncoderClassifier
from auth.voice.vad import remove_silence
import torch
import os

SAMPLE_RATE = 16000
DURATION = 5
NUM_CLIPS = 2

TEMP_FILE = "temp_verify.wav"

classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="models/ecapa"
)

owner_embedding = np.load("data/voice_profile/owner_embedding.npy")
owner_embedding = owner_embedding / np.linalg.norm(owner_embedding)

embeddings = []

for i in range(NUM_CLIPS):

    print(f"Recording verification sample {i+1}...")

    audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()

    write(TEMP_FILE, SAMPLE_RATE, audio)

    signal, fs = torchaudio.load(TEMP_FILE)

    # convert to numpy
    audio_np = signal.squeeze().numpy()

    # remove silence using VAD
    audio_np = remove_silence(audio_np)

    # convert back to tensor
    signal = torch.tensor(audio_np).unsqueeze(0)

    # generate embedding
    emb = classifier.encode_batch(signal).squeeze().detach().numpy()

    emb = emb / np.linalg.norm(emb)

    embeddings.append(emb)

# average verification embeddings
verification_embedding = np.mean(embeddings, axis=0)
verification_embedding = verification_embedding / np.linalg.norm(verification_embedding)

similarity = np.dot(verification_embedding, owner_embedding)

print("Similarity:", similarity)

THRESHOLD = 0.50

if similarity > THRESHOLD:
    print("Access granted")
else:
    print("Access denied")

os.remove(TEMP_FILE)