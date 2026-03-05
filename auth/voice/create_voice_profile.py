import os
import numpy as np
import torchaudio
from speechbrain.pretrained import EncoderClassifier

classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="models/ecapa"
)

sample_dir = "data/voice_samples"

embeddings = []

for file in os.listdir(sample_dir):

    if file.endswith(".wav"):

        path = os.path.join(sample_dir, file)

        signal, fs = torchaudio.load(path)

        emb = classifier.encode_batch(signal).squeeze().detach().numpy()

        emb = emb / np.linalg.norm(emb)

        embeddings.append(emb)

embeddings = np.array(embeddings)

np.save("data/voice_profile/owner_embeddings.npy", embeddings)

print("Stored embeddings:", embeddings.shape)