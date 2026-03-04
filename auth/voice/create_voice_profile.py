from speechbrain.pretrained import EncoderClassifier
import torch
import numpy as np
import soundfile as sf
import os

# Get the script's directory and build paths from there
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir=os.path.join(project_root, "models", "ecapa")
)

sample_dir = os.path.join(project_root, "data", "voice_samples")
embeddings = []

for file in sorted(os.listdir(sample_dir)):

    if file.endswith(".wav"):

        path = os.path.join(sample_dir, file)

        audio, fs = sf.read(path)
        signal = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)

        embedding = classifier.encode_batch(signal)

        embeddings.append(embedding.squeeze().detach().numpy())

print("Samples processed:", len(embeddings))

final_embedding = np.mean(embeddings, axis=0)

print("Embedding size:", final_embedding.shape)

profile_dir = os.path.join(project_root, "data", "voice_profile")
os.makedirs(profile_dir, exist_ok=True)
np.save(os.path.join(profile_dir, "owner_embedding.npy"), final_embedding)

print("Voice profile saved.")