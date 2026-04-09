import subprocess
import sys
import time
import pyaudio
import numpy as np

is_speaking     = False
_speech_process = None

def speak(text: str) -> bool:
    global is_speaking
    is_speaking = True
    print(f"🔊 Jarvis: {text}")
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        # Try to find a good voice
        for voice in voices:
            if 'david' in voice.name.lower() or 'mark' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break
        engine.setProperty('rate', 180)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"❌ TTS error: {e}")
    is_speaking = False
    return True   # Windows version not interruptible yet

def speak_and_wait(text: str) -> None:
    speak(text)