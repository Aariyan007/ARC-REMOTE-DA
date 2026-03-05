import webrtcvad
import numpy as np


def remove_silence(audio, sample_rate=16000, frame_duration=30):
    vad = webrtcvad.Vad(2)

    frame_size = int(sample_rate * frame_duration / 1000)

    speech_frames = []

    for i in range(0, len(audio), frame_size):
        frame = audio[i:i + frame_size]

        if len(frame) < frame_size:
            continue

        frame_bytes = (frame * 32768).astype("int16").tobytes()

        if vad.is_speech(frame_bytes, sample_rate):
            speech_frames.append(frame)

    if len(speech_frames) == 0:
        return audio

    return np.concatenate(speech_frames)