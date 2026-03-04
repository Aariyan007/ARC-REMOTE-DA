import numpy as np
import torchaudio
import sounddevice as sd
from scipy.io.wavfile import write
from speechbrain.pretrained import EncoderClassifier
import os

SAMPLE_RATE = 16000
DURATION = 4

TEMP_FILE = "temp_verify.wav"

print("Speak for verification...")

# record audio
audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
sd.wait()

# save temporary wav
write(TEMP_FILE, SAMPLE_RATE, audio)

# load ECAPA model
classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="models/ecapa"
)

# load recorded audio
signal, fs = torchaudio.load(TEMP_FILE)

# generate embedding
embedding = classifier.encode_batch(signal).squeeze().detach().numpy()

# load stored owner embedding
owner_embedding = np.load("data/voice_profile/owner_embedding.npy")

# normalize embeddings
embedding = embedding / np.linalg.norm(embedding)
owner_embedding = owner_embedding / np.linalg.norm(owner_embedding)

# cosine similarity
similarity = np.dot(embedding, owner_embedding)

print("Similarity score:", similarity)

THRESHOLD = 0.60

if similarity > THRESHOLD:
    print("Access granted")
else:
    print("Access denied")
    
os.remove(TEMP_FILE)