import sounddevice as sd
from scipy.io.wavfile import write
import os

SAMPLE_RATE = 16000
DURATION = 6
NUM_SAMPLES = 8

# Get the script's directory and build path from there
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
save_dir = os.path.join(project_root, "data", "voice_samples")
os.makedirs(save_dir, exist_ok=True)

print("\nVoice Enrollment for Jarvis\n")

for i in range(NUM_SAMPLES):

    input(f"\nPress ENTER to record sample {i+1}")

    print("Recording...")

    audio = sd.rec(int(DURATION * SAMPLE_RATE),
                   samplerate=SAMPLE_RATE,
                   channels=1)

    sd.wait()

    filename = f"{save_dir}/sample_{i+1}.wav"

    write(filename, SAMPLE_RATE, audio)

    print("Saved:", filename)

print("\nEnrollment recordings complete.")