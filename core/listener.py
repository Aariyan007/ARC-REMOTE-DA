import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from auth.voice.verify_voice import verify_voice

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280

model = None
try:
    model = Model(
        wakeword_models=["hey_mycroft"],
        inference_framework="onnx"
    )
except Exception as e:
    print(f"Warning: Could not load wake word model: {e}")
    print("Running in demo mode - wake word detection disabled")


def start_listener():

    print("Jarvis listening...")

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        blocksize=CHUNK_SIZE,
        dtype="int16"
    )

    with stream:

        while True:

            audio, _ = stream.read(CHUNK_SIZE)

            if model is None:
                print("Wake word model not available - demo mode active")
                print("Proceeding with voice verification...")
                if verify_voice():
                    print("Owner verified")
                    return True
                else:
                    print("Unknown speaker ignored")
                break

            prediction = model.predict(audio.flatten())

            score = prediction["hey_mycroft"]

            if score > 0.5:

                print("Wake word detected")

                if verify_voice():

                    print("Owner verified")
                    return True
                else:
                    print("Unknown speaker ignored")