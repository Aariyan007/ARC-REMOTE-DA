import os
import pvporcupine
import sounddevice as sd
import numpy as np
from dotenv import load_dotenv
from auth.voice.verify_voice import verify_voice

load_dotenv()
ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY")  # Get your own from https://console.picovoice.ai/

def start_listener():
    porcupine = pvporcupine.create(
        access_key=ACCESS_KEY,
        keywords=["jarvis"]   # built-in, no model files needed
    )

    print("[listener] Jarvis is listening...")

    stream = sd.InputStream(
        samplerate=porcupine.sample_rate,  # 16000
        channels=1,
        blocksize=porcupine.frame_length,  # 512
        dtype="int16"
    )

    with stream:
        while True:
            audio, _ = stream.read(porcupine.frame_length)
            result = porcupine.process(audio.flatten())

            if result >= 0:
                print("[listener] Wake word detected!")
                if verify_voice():
                    print("[listener] Owner verified ✓")
                    porcupine.delete()
                    return True
                else:
                    print("[listener] Unknown speaker — resuming...")