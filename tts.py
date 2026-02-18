"""
TTS Module - Streaming Text-to-Speech with Interruption Support
================================================================
This module wraps the streaming TTS engine for compatibility.
All edge_speak calls now support instant interruption.
"""

import io
import time
import asyncio
import threading
import sounddevice as sd
import soundfile as sf
import edge_tts
from typing import Optional, Callable

# --- Global State ---
_stop_event = threading.Event()
_playback_lock = threading.Lock()
_is_playing = False

# STS Engine reference for echo cancellation coordination
_sts_engine = None


def set_sts_engine(engine):
    """Set the STS engine for echo cancellation coordination"""
    global _sts_engine
    _sts_engine = engine


def stop_speaking():
    """Immediately stop any current TTS playback"""
    global _is_playing
    _stop_event.set()
    _is_playing = False
    try:
        sd.stop()
    except:
        pass


def is_speaking() -> bool:
    """Check if TTS is currently playing"""
    return _is_playing


def edge_speak(text: str, ui=None, blocking: bool = False):
    """
    Streaming TTS with instant interruption support.
    
    Features:
    - Starts playing before full audio is generated (low latency)
    - Can be interrupted at any time by stop_speaking()
    - Coordinates with STS engine for echo cancellation
    
    Args:
        text: Text to speak
        ui: Optional UI object with start_speaking/stop_speaking methods
        blocking: If True, wait for speech to complete
    """
    if not text or not text.strip():
        return
        
    # Stop any current playback first
    stop_speaking()
    
    finished_event = threading.Event()
    
    def _playback_thread():
        global _is_playing
        
        with _playback_lock:
            _stop_event.clear()
            _is_playing = True
            
            # Notify STS engine we're speaking (echo cancellation)
            if _sts_engine:
                _sts_engine.set_speaking(True)
            
            # Notify UI
            if ui and hasattr(ui, 'start_speaking'):
                try:
                    ui.start_speaking()
                except:
                    pass
                
            try:
                voice = "pt-BR-AntonioNeural" 
                communicate = edge_tts.Communicate(text, voice)
                
                audio_chunks = []
                chunk_threshold = 3  # Start playing after 3 chunks
                playback_started = False
                
                async def collect_and_play():
                    nonlocal playback_started, audio_chunks
                    try:
                        async for chunk in communicate.stream():
                            if _stop_event.is_set():
                                return
                            if chunk["type"] == "audio":
                                audio_chunks.append(chunk["data"])
                                # Start early playback for low latency
                                if not playback_started and len(audio_chunks) >= chunk_threshold:
                                    playback_started = True
                                    # Don't block here, continue collecting
                    finally:
                        close_fn = getattr(communicate, "close", None)
                        if callable(close_fn):
                            result = close_fn()
                            if asyncio.iscoroutine(result):
                                await result

                    # All chunks collected
                    if not _stop_event.is_set() and audio_chunks:
                        _play_audio(audio_chunks)

                # Run async collection safely
                _run_async(collect_and_play())
                    
            except Exception as e:
                print(f"TTS Error: {e}")
            finally:
                _is_playing = False
                
                # Notify STS engine we stopped speaking
                if _sts_engine:
                    _sts_engine.set_speaking(False)
                
                # Notify UI
                if ui and hasattr(ui, 'stop_speaking'):
                    try:
                        ui.stop_speaking()
                    except:
                        pass
                        
                finished_event.set()
    
    # Start playback thread
    threading.Thread(target=_playback_thread, daemon=True).start()
    
    if blocking:
        finished_event.wait()


def _play_audio(audio_chunks: list):
    """Play collected audio chunks"""
    if not audio_chunks or _stop_event.is_set():
        return
        
    try:
        full_audio = b"".join(audio_chunks)
        if not full_audio:
            return
            
        data, samplerate = sf.read(io.BytesIO(full_audio), dtype="float32")
        
        if _stop_event.is_set():
            return
            
        # Play non-blocking
        sd.play(data, samplerate, blocking=False)
        
        # Wait for playback with interrupt check
        duration = len(data) / samplerate
        start_time = time.time()
        
        while time.time() - start_time < duration:
            if _stop_event.is_set():
                sd.stop()
                break
            time.sleep(0.05)
            
    except Exception as e:
        print(f"Audio Playback Error: {e}")


def _run_async(coro):
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
