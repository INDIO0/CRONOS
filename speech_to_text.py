import os
import io
import time
import wave
import threading
from collections import deque

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL") or "whisper-large-v3"
GROQ_STT_LANGUAGE = os.getenv("GROQ_STT_LANGUAGE") or "pt"
GROQ_STT_TEMPERATURE = float(os.getenv("GROQ_STT_TEMPERATURE", "0"))
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Audio config (env overrides)
SAMPLE_RATE = int(os.getenv("CRONO_STT_SAMPLE_RATE", "16000"))
CHUNK_DURATION = float(os.getenv("CRONO_STT_CHUNK_DURATION", "0.25"))
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)
SILENCE_THRESHOLD = int(os.getenv("CRONO_STT_SILENCE_THRESHOLD", "800"))
SILENCE_CHUNKS = int(os.getenv("CRONO_STT_SILENCE_CHUNKS", "6"))
MAX_RECORD_SECONDS = float(os.getenv("CRONO_STT_MAX_RECORD_SECONDS", "10"))
SPEECH_START_TIMEOUT = float(os.getenv("CRONO_STT_START_TIMEOUT", "8"))
AMBIENT_CALIBRATION_SECONDS = float(os.getenv("CRONO_STT_AMBIENT_SECONDS", "1.0"))
ADAPTIVE_NOISE_MULTIPLIER = float(os.getenv("CRONO_STT_NOISE_MULT", "2.0"))
MIN_SPEECH_SECONDS = float(os.getenv("CRONO_STT_MIN_SPEECH_SECONDS", "0.4"))

stop_listening_flag = threading.Event()


def calculate_energy(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def _calibrate_noise_floor(stream: sd.InputStream) -> float:
    """Estimate ambient noise to build a dynamic threshold."""
    if AMBIENT_CALIBRATION_SECONDS <= 0:
        return float(SILENCE_THRESHOLD)
    total_chunks = max(1, int(AMBIENT_CALIBRATION_SECONDS / CHUNK_DURATION))
    energies = []
    for _ in range(total_chunks):
        if stop_listening_flag.is_set():
            break
        chunk, _ = stream.read(CHUNK_SIZE)
        energies.append(calculate_energy(chunk))
    if not energies:
        return float(SILENCE_THRESHOLD)
    baseline = float(np.median(energies))
    return max(float(SILENCE_THRESHOLD), baseline * ADAPTIVE_NOISE_MULTIPLIER)


def stop_listening():
    stop_listening_flag.set()


def reset_listening():
    stop_listening_flag.clear()


def record_voice(prompt=None) -> str:
    """
    Capture microphone audio with adaptive VAD and transcribe using Groq.
    Returns a lowercased string or "" if nothing recognized.
    """
    if not client:
        return ""

    audio_buffer = deque()
    silence_counter = 0
    recording = False
    record_start = None

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.int16,
            blocksize=CHUNK_SIZE,
        ) as stream:
            threshold = _calibrate_noise_floor(stream)
            start_time = time.time()

            while not stop_listening_flag.is_set():
                if not recording and (time.time() - start_time) > SPEECH_START_TIMEOUT:
                    return ""

                chunk, _ = stream.read(CHUNK_SIZE)
                energy = calculate_energy(chunk)

                if not recording and energy > threshold:
                    recording = True
                    record_start = time.time()
                    audio_buffer.clear()
                    silence_counter = 0

                if recording:
                    audio_buffer.append(chunk)

                    if energy < threshold:
                        silence_counter += 1
                        if silence_counter >= SILENCE_CHUNKS:
                            break
                    else:
                        silence_counter = 0

                    if record_start and (time.time() - record_start) >= MAX_RECORD_SECONDS:
                        break

        if not recording:
            return ""

        if record_start and (time.time() - record_start) < MIN_SPEECH_SECONDS:
            return ""

        if len(audio_buffer) < 2:
            return ""

        full_audio = np.concatenate(list(audio_buffer))
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(full_audio.tobytes())
        wav_buffer.seek(0)

        transcription = client.audio.transcriptions.create(
            file=("audio.wav", wav_buffer.read()),
            model=GROQ_STT_MODEL,
            language=GROQ_STT_LANGUAGE,
            temperature=GROQ_STT_TEMPERATURE,
            response_format="json",
        )

        text = transcription.text.strip().lower()
        hallucinations = {
            "[silencio]",
            "[pausa]",
            "[silence]",
            "[pause]",
        }
        if text in hallucinations:
            return ""
        if len(text) < 2:
            return ""
        return text

    except Exception:
        return ""
