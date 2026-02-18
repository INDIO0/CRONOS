"""
Streaming TTS Engine
====================
Low-latency Text-to-Speech with:
- Streaming audio generation
- Instant interruption support
- Echo cancellation coordination
- Chunked playback for better responsiveness
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
_current_stream: Optional[sd.OutputStream] = None
_is_playing = False

# Callbacks
_on_start_speaking: Optional[Callable] = None
_on_stop_speaking: Optional[Callable] = None


def set_callbacks(on_start: Callable = None, on_stop: Callable = None):
    """Set UI callbacks for speaking state"""
    global _on_start_speaking, _on_stop_speaking
    _on_start_speaking = on_start
    _on_stop_speaking = on_stop


def stop_speaking():
    """Immediately stop any current TTS playback"""
    global _is_playing
    _stop_event.set()
    _is_playing = False
    sd.stop()


def is_speaking() -> bool:
    """Check if TTS is currently playing"""
    return _is_playing


def streaming_speak(text: str, ui=None, blocking: bool = False):
    """
    Streaming TTS with chunked playback for low latency.
    
    Features:
    - Starts playing before full audio is generated
    - Can be interrupted at any time
    - Coordinates with STS engine for echo cancellation
    """
    if not text or not text.strip():
        return
        
    # Stop any current playback
    stop_speaking()
    
    finished_event = threading.Event()
    
    def _playback_thread():
        global _is_playing
        
        with _playback_lock:
            _stop_event.clear()
            _is_playing = True
            
            if ui and hasattr(ui, 'start_speaking'):
                ui.start_speaking()
            elif _on_start_speaking:
                _on_start_speaking()
                
            try:
                voice = "pt-BR-AntonioNeural"  
                communicate = edge_tts.Communicate(text, voice)
                audio_chunks = []
                
                async def stream_audio():
                    try:
                        async for chunk in communicate.stream():
                            if _stop_event.is_set():
                                return
                            if chunk["type"] == "audio":
                                audio_chunks.append(chunk["data"])
                    finally:
                        close_fn = getattr(communicate, "close", None)
                        if callable(close_fn):
                            result = close_fn()
                            if asyncio.iscoroutine(result):
                                await result

                    if audio_chunks and not _stop_event.is_set():
                        _start_playback(audio_chunks, threaded=False)

                # Run the async streaming safely
                _run_async(stream_audio())
                    
            except Exception as e:
                print(f"Streaming TTS Error: {e}")
            finally:
                _is_playing = False
                if ui and hasattr(ui, 'stop_speaking'):
                    ui.stop_speaking()
                elif _on_stop_speaking:
                    _on_stop_speaking()
                finished_event.set()
    
    # Start playback thread
    threading.Thread(target=_playback_thread, daemon=True).start()
    
    if blocking:
        finished_event.wait()


def _start_playback(audio_chunks: list, threaded: bool = False):
    """Start playing accumulated audio chunks"""
    if not audio_chunks or _stop_event.is_set():
        return
        
    try:
        full_audio = b"".join(audio_chunks)
        if not full_audio:
            return
            
        data, samplerate = sf.read(io.BytesIO(full_audio), dtype="float32")
        
        if _stop_event.is_set():
            return
            
        sd.play(data, samplerate, blocking=not threaded)
        
    except Exception as e:
        print(f"Playback Error: {e}")


def _wait_for_playback():
    """Wait for current playback to finish or be interrupted"""
    while sd.get_stream() is not None:
        if _stop_event.is_set():
            sd.stop()
            break
        time.sleep(0.05)
        
        # Check if still playing
        try:
            status = sd.get_status()
            if not status.active:
                break
        except:
            break


# Compatibility wrapper for existing code
def edge_speak(text: str, ui=None, blocking: bool = False):
    """Wrapper for compatibility with existing tts.py interface"""
    streaming_speak(text, ui, blocking)


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
