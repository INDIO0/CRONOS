"""
STS Engine - Full-Duplex Speech-to-Speech Engine
=================================================
Inspired by Moshi's full-duplex architecture.
Enables natural conversation with:
- Continuous listening (even during TTS playback)
- Instant interruption
- Low-latency streaming pipeline
- Echo cancellation
"""

import os
import io
import wave
import time
import asyncio
import threading
import numpy as np
import sounddevice as sd
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# --- Configuration ---
SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30  # 30ms frames (like Moshi's design)
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)
SILENCE_THRESHOLD = int(os.getenv("CRONO_SILENCE_THRESHOLD", "250"))  # Base energy threshold (more sensitive)
SPEECH_START_FRAMES = int(os.getenv("CRONO_SPEECH_START_FRAMES", "2"))  # Frames to confirm start (faster)
SILENCE_END_FRAMES = int(os.getenv("CRONO_SILENCE_END_FRAMES", "16"))  # ~480ms of silence to confirm end
MAX_RECORDING_FRAMES = 500  # ~15s max

# Barge-in (talk-over) tuning for notebook speakers/mic
BARGE_IN_GUARD_MS = 250  # ignore detection just after TTS starts
BARGE_IN_COOLDOWN_MS = 350  # ignore mic briefly after TTS stops
BARGE_IN_MULTIPLIER = 1.6  # how much louder than TTS baseline user speech must be
BARGE_IN_DELTA = 200  # additional absolute margin
TTS_BASELINE_EMA_ALPHA = 0.15  # smoothing for TTS baseline energy

# Adaptive noise floor (reduce false positives)
NOISE_FLOOR_EMA_ALPHA = 0.08
NOISE_FLOOR_MULTIPLIER = 1.8
NOISE_FLOOR_MARGIN = 40

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL") or "whisper-large-v3"
GROQ_STT_LANGUAGE = os.getenv("GROQ_STT_LANGUAGE") or "pt"
GROQ_STT_TEMPERATURE = float(os.getenv("GROQ_STT_TEMPERATURE", "0"))
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


class STSEngine:
    """
    Full-Duplex Speech-to-Speech Engine

    Features:
    - Continuous VAD (Voice Activity Detection)
    - Echo cancellation during TTS playback
    - Instant interruption support
    - Streaming pipeline for low latency
    """

    def __init__(self):
        # State flags
        self.running = False
        self.is_speaking = False  # TTS is playing
        self.is_listening = True
        self.interrupt_requested = False

        # udio buffers
        self.audio_buffer = deque(maxlen=MAX_RECORDING_FRAMES)
        self.tts_audio_playing = False
        self._audio_stream = None

        # Callbacks
        self.on_speech_start: Optional[Callable] = None
        self.on_speech_end: Optional[Callable[[str], None]] = None
        self.on_interrupt: Optional[Callable] = None

        # Threading
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._stop_event = threading.Event()
        self._audio_thread = None
        self._vad_lock = threading.Lock()

        # VAD state
        self._speech_frames = 0
        self._silence_frames = 0
        self._is_recording = False

        # Echo cancellation
        self._echo_threshold_boost = 200  # Boost threshold during TTS
        self._tts_energy_ema = 0.0
        self._tts_energy_initialized = False
        self._tts_started_at = 0.0
        self._ignore_until = 0.0
        self._noise_floor_ema = 0.0
        self._noise_floor_initialized = False

        # Debug/stats
        self._total_frames = 0
        self._detected_speech_count = 0
        self.last_energy = 0.0

    def start(self):
        """Start the STS engine"""
        if self.running:
            print("AVISO STS - Engine jestrodando")
            return

        self.running = True
        self._stop_event.clear()
        self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True, name="STS-udio-Loop")
        self._audio_thread.start()
        print("STS Engine iniciado")

    def stop(self):
        """Stop the STS engine"""
        if not self.running:
            print("AVISO STS - Engine jestparado")
            return

        self.running = False
        self._stop_event.set()

        # Aguarda thread finalizar (timeout 5s)
        if self._audio_thread and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=5)

        # Fecha stream se aberto
        if self._audio_stream:
            try:
                self._audio_stream.close()
            except Exception as e:
                print(f"AVISO - Erro ao fechar stream: {e}")

        # Encerra executor
        try:
            self._executor.shutdown(wait=False, timeout=2)
        except Exception as e:
            print(f"AVISO - Erro ao desligar executor: {e}")

        print("STS Engine parado")

    def set_speaking(self, speaking: bool):
        """Notify engine that TTS is playing (for echo cancellation)"""
        with self._vad_lock:
            self.is_speaking = speaking
            self.tts_audio_playing = speaking
            if speaking:
                self._tts_started_at = time.time()
                self._tts_energy_initialized = False
            else:
                self._tts_energy_initialized = False
                self._tts_energy_ema = 0.0
                # Cooldown to avoid immediate echo pickup
                self._ignore_until = time.time() + (BARGE_IN_COOLDOWN_MS / 1000.0)

    def request_interrupt(self):
        """Request to interrupt current TTS playback"""
        self.interrupt_requested = True
        if self.on_interrupt:
            self.on_interrupt()

    def set_listening(self, listening: bool):
        """Enable/disable mic processing without stopping the audio stream."""
        with self._vad_lock:
            self.is_listening = bool(listening)
            if not self.is_listening:
                self._is_recording = False
                self.audio_buffer.clear()
                self._speech_frames = 0
                self._silence_frames = 0

    def _get_effective_threshold(self) -> float:
        """Get VAD threshold with echo cancellation boost"""
        base = SILENCE_THRESHOLD
        if self._noise_floor_initialized:
            base = max(base, (self._noise_floor_ema * NOISE_FLOOR_MULTIPLIER) + NOISE_FLOOR_MARGIN)
        if self.is_speaking:
            return base + self._echo_threshold_boost
        return base

    def get_vad_threshold(self) -> float:
        return self._get_effective_threshold()

    def _is_barge_in_speech(self, energy: float, base_threshold: float) -> bool:
        """Detect user speech while TTS is playing using dynamic baseline."""
        # Guard window right after TTS starts
        if self._tts_started_at and (time.time() - self._tts_started_at) < (BARGE_IN_GUARD_MS / 1000.0):
            return False

        # Initialize or update baseline during TTS playback
        if not self._tts_energy_initialized:
            self._tts_energy_ema = energy
            self._tts_energy_initialized = True
        else:
            self._tts_energy_ema = (
                (1.0 - TTS_BASELINE_EMA_ALPHA) * self._tts_energy_ema
                + TTS_BASELINE_EMA_ALPHA * energy
            )

        # Require energy to be meaningfully above the TTS baseline
        dynamic_threshold = max(
            base_threshold,
            (self._tts_energy_ema * BARGE_IN_MULTIPLIER) + BARGE_IN_DELTA
        )
        return energy > dynamic_threshold

    def _calculate_energy(self, audio: np.ndarray) -> float:
        """Calculate RMS energy of audio frame"""
        if len(audio) == 0:
            return 0.0
        try:
            return np.sqrt(np.mean(audio.astype(np.float32) ** 2))
        except Exception as e:
            print(f"AVISO - Erro ao calcular energia: {e}")
            return 0.0

    def _audio_loop(self):
        """Main audio processing loop - runs continuously"""
        try:
            device = os.getenv("CRONO_INPUT_DEVICE")
            device_index = None
            if device:
                try:
                    if str(device).isdigit():
                        device_index = int(device)
                    else:
                        for idx, info in enumerate(sd.query_devices()):
                            name = str(info.get("name") or "")
                            if device.lower() in name.lower() and info.get("max_input_channels", 0) > 0:
                                device_index = idx
                                break
                    if device_index is not None:
                        sd.default.device = (device_index, None)
                        print(f"STS usando dispositivo de entrada: {device_index}")
                except Exception as e:
                    print(f"AVISO - Falha ao configurar CRONO_INPUT_DEVICE: {e}")
            try:
                print(f"Dispositivo padrão de áudio: {sd.default.device}")
            except Exception:
                pass

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype=np.int16,
                blocksize=FRAME_SIZE,
                latency='low',
                device=device_index
            ) as stream:
                self._audio_stream = stream
                print(f"Stream de udio aberto - Taxa: {SAMPLE_RATE}Hz, Frame: {FRAME_SIZE}")

                while self.running and not self._stop_event.is_set():
                    try:
                        # Read a frame
                        frame, overflowed = stream.read(FRAME_SIZE)
                        if overflowed:
                            print("AVISO - udio overflow detectado")

                        if frame is None or len(frame) == 0:
                            continue

                        energy = self._calculate_energy(frame)
                        threshold = self._get_effective_threshold()
                        self._total_frames += 1

                        self._process_frame(frame, energy, threshold)

                    except Exception as frame_error:
                        print(f"AVISO - Erro ao processar frame: {frame_error}")
                        continue

        except Exception as e:
            print(f"ERRO STS - udio Loop: {type(e).__name__}: {e}")
            try:
                print("Dispositivos de udio disponveis:")
                for i, info in enumerate(sd.query_devices()):
                    print(f"  [{i}] {info.get('name')} (in={info.get('max_input_channels')}, out={info.get('max_output_channels')})")
            except Exception:
                pass
            import traceback
            traceback.print_exc()
        finally:
            self._audio_stream = None
            print("Stream de udio fechado")

    def _process_frame(self, frame: np.ndarray, energy: float, threshold: float):
        """Process a single audio frame through VAD"""
        with self._vad_lock:
            self.last_energy = float(energy)
            if not self.is_listening:
                if self._is_recording:
                    self._is_recording = False
                    self.audio_buffer.clear()
                self._speech_frames = 0
                self._silence_frames = 0
                return
            # Ignore mic briefly after TTS stops
            if self._ignore_until and time.time() < self._ignore_until:
                if self._is_recording:
                    self._is_recording = False
                    self.audio_buffer.clear()
                self._speech_frames = 0
                self._silence_frames = 0
                return

            # Update adaptive noise floor when idle (avoid speech frames)
            if not self.is_speaking and not self._is_recording:
                if not self._noise_floor_initialized:
                    self._noise_floor_ema = float(energy)
                    self._noise_floor_initialized = True
                else:
                    if energy <= (SILENCE_THRESHOLD * 1.2):
                        self._noise_floor_ema = (
                            (1.0 - NOISE_FLOOR_EMA_ALPHA) * self._noise_floor_ema
                            + NOISE_FLOOR_EMA_ALPHA * float(energy)
                        )

            if self.is_speaking:
                is_speech = self._is_barge_in_speech(energy, threshold)
            else:
                is_speech = energy > threshold

            # If TTS is speaking and no barge-in speech detected, ignore completely
            if self.is_speaking and not is_speech:
                if self._is_recording:
                    self._is_recording = False
                    self.audio_buffer.clear()
                self._speech_frames = 0
                self._silence_frames = 0
                return

            if not self._is_recording:
                # Not recording - waiting for speech
                if is_speech:
                    self._speech_frames += 1
                    if self._speech_frames >= SPEECH_START_FRAMES:
                        # Speech confirmed - start recording
                        self._is_recording = True
                        self._silence_frames = 0
                        self.audio_buffer.clear()
                        self.audio_buffer.append(frame)
                        self._detected_speech_count += 1

                        # If TTS is playing, request interrupt
                        if self.is_speaking:
                            self.request_interrupt()

                        if self.on_speech_start:
                            try:
                                self._executor.submit(self.on_speech_start)
                            except Exception as e:
                                print(f"AVISO - Erro ao chamar on_speech_start: {e}")
                else:
                    self._speech_frames = max(0, self._speech_frames - 1)  # Decay
            else:
                # Recording - collect audio
                self.audio_buffer.append(frame)

                if is_speech:
                    self._silence_frames = 0
                else:
                    self._silence_frames += 1

                    # Check if speech ended
                    if self._silence_frames >= SILENCE_END_FRAMES:
                        self._finish_recording()

                # Check max recording length
                if len(self.audio_buffer) >= MAX_RECORDING_FRAMES:
                    self._finish_recording()

    def _finish_recording(self):
        """Finish recording and transcribe"""
        self._is_recording = False
        self._speech_frames = 0
        self._silence_frames = 0

        buffer_size = len(self.audio_buffer)
        if buffer_size > 5:  # At least ~150ms of audio
            try:
                audio_data = np.concatenate(list(self.audio_buffer))
                self._executor.submit(self._transcribe_async, audio_data.copy())
            except Exception as e:
                print(f"[WARN] Erro ao preparar audio para transcricao: {e}")
        else:
            print(f"[WARN] Buffer muito pequeno ({buffer_size} frames), descartando")

        self.audio_buffer.clear()

    def _transcribe_async(self, audio_data: np.ndarray):
        """Transcribe audio asynchronously using Groq Whisper"""
        if not groq_client:
            print("[ERROR] STS: Groq client nao inicializado. Verifique GROQ_API_KEY")
            return

        if audio_data is None or len(audio_data) == 0:
            print("[WARN] Audio vazio para transcricao")
            return

        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_data.tobytes())
            wav_buffer.seek(0)

            transcription = groq_client.audio.transcriptions.create(
                file=("audio.wav", wav_buffer.read()),
                model=GROQ_STT_MODEL,
                language=GROQ_STT_LANGUAGE,
                temperature=GROQ_STT_TEMPERATURE,
                response_format="json",
            )

            text = transcription.text.strip().lower()
            hallucinations = {
                "obrigado", "muito obrigado", "de nada", "valeu",
                "thank you", "thanks for watching", "you're welcome",
                "thanks", "bye", "tchau", "...", "[silncio]", "[pausa]"
            }

            if text in hallucinations or len(text) < 2:
                return

            print(f"[STT] Transcricao: '{text}'")

            if self.on_speech_end:
                try:
                    self.on_speech_end(text)
                except Exception as cb_err:
                    print(f"[WARN] Erro no callback on_speech_end: {cb_err}")

        except Exception as e:
            print(f"[ERROR] STS - Transcricao: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()


class StreamingPipeline:
    """
    Streaming pipeline for low-latency processing.
    Coordinates STT -> LLM -> TTS with parallelism.
    """

    def __init__(self, sts_engine: STSEngine):
        self.engine = sts_engine
        self._processing = False
        self._pending_text: Optional[str] = None
        self._lock = threading.Lock()
        print("[INFO] StreamingPipeline inicializado")

    async def process_streaming(
        self,
        text: str,
        llm_func: Callable,
        tts_func: Callable,
        action_func: Optional[Callable] = None
    ):
        """
        Process user text through the pipeline with streaming.

        Args:
            text: User's transcribed speech
            llm_func: Function to call LLM (should return response dict)
            tts_func: Function to speak text (streaming TTS)
            action_func: Optional function to execute actions
        """
        with self._lock:
            if self._processing:
                self._pending_text = text
                return
            self._processing = True

        try:
            # Call LLM
            llm_output = await asyncio.to_thread(llm_func, text)

            # Validate LLM output
            if not llm_output or not isinstance(llm_output, dict):
                print("[WARN] LLM retornou output invalido")
                return

            # Check if interrupted during LLM call
            if self.engine.interrupt_requested:
                self.engine.interrupt_requested = False
                print("[INFO] Processamento interrompido pelo usuario")
                return

            response_text = llm_output.get("text", "")
            intent = llm_output.get("intent", "chat")
            params = llm_output.get("parameters", {})

            if not response_text:
                print("[WARN] LLM retornou texto vazio")
                return

            # Execute action if needed (in parallel with TTS start)
            if action_func and intent != "chat":
                try:
                    asyncio.create_task(
                        asyncio.to_thread(action_func, intent, params, response_text)
                    )
                except Exception as action_err:
                    print(f"[WARN] Erro ao executar acao: {action_err}")

            # Start TTS (streaming)
            if response_text:
                self.engine.set_speaking(True)
                try:
                    await asyncio.to_thread(tts_func, response_text)
                except Exception as tts_err:
                    print(f"[WARN] Erro ao executar TTS: {tts_err}")
                finally:
                    self.engine.set_speaking(False)

        except Exception as e:
            print(f"ERRO STS - Pipeline: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            with self._lock:
                self._processing = False

            # Process pending text if any
            if self._pending_text:
                pending = self._pending_text
                self._pending_text = None
                await self.process_streaming(pending, llm_func, tts_func, action_func)


# Singleton instance
_engine_instance: Optional[STSEngine] = None


def get_sts_engine() -> STSEngine:
    """Get or create the STS engine singleton"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = STSEngine()
        print("STSEngine singleton criado")
    return _engine_instance


def get_engine_stats() -> dict:
    """Get engine statistics for debugging"""
    engine = get_sts_engine()
    return {
        "running": engine.running,
        "is_speaking": engine.is_speaking,
        "is_listening": engine.is_listening,
        "buffer_size": len(engine.audio_buffer),
        "total_frames_processed": engine._total_frames,
        "speech_detected_count": engine._detected_speech_count,
        "is_recording": engine._is_recording,
    }
