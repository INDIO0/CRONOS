# sts/sts_system.py
"""
STS System - Unified Speech-to-Speech Engine
=============================================
Wrapper que gerencia todos os componentes STS (STT, TTS, VAD)
com mtricas, resilincia e callbacks.

Mantm os modelos existentes (sts_engine.py, streaming_tts.py, speech_to_text.py)
sem modificao e adiciona camada superior.
"""

import os
import time
import threading
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime
from collections import deque
from dotenv import load_dotenv

load_dotenv()

# Import dos modelos existentes (sem modificao)
from sts_engine import get_sts_engine
from streaming_tts import streaming_speak, stop_speaking
from speech_to_text import record_voice, reset_listening


class AudioMetrics:
    """Rastreador de mtricas de udio."""
    
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.history: deque = deque(maxlen=max_history)
        self.total_stt_requests = 0
        self.successful_stt = 0
        self.total_tts_requests = 0
        self.total_listening_time = 0.0  # garantir float
        self.total_speaking_time = 0.0   # garantir float
        self._lock = threading.Lock()
    
    def record_stt(self, success: bool, duration: float, text: str = ""):
        """Registrar requisio STT."""
        with self._lock:
            self.total_stt_requests += 1
            if success:
                self.successful_stt += 1
            
            self.history.append({
                "type": "stt",
                "success": success,
                "duration": duration,
                "text": text[:50],  # Primeiros 50 chars
                "timestamp": time.time()
            })
    
    def record_tts(self, duration: float, text: str = ""):
        """Registrar requisio TTS."""
        with self._lock:
            self.total_tts_requests += 1
            
            self.history.append({
                "type": "tts",
                "duration": duration,
                "text": text[:50],
                "timestamp": time.time()
            })
    
    def record_listening(self, duration: float):
        """Registrar tempo de escuta."""
        with self._lock:
            self.total_listening_time += duration
    
    def record_speaking(self, duration: float):
        """Registrar tempo de fala."""
        with self._lock:
            self.total_speaking_time += duration
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatsticas completas."""
        with self._lock:
            stt_rate = (self.successful_stt / self.total_stt_requests * 100) if self.total_stt_requests else 0.0
            return {
                "total_stt_requests": self.total_stt_requests,
                "successful_stt": self.successful_stt,
                "stt_success_rate": round(stt_rate, 2),
                "total_tts_requests": self.total_tts_requests,
                "total_listening_time_seconds": round(self.total_listening_time, 2),
                "total_speaking_time_seconds": round(self.total_speaking_time, 2),
                "history_entries": len(self.history)
            }
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obter histrico recente."""
        with self._lock:
            return list(self.history)[-limit:]
    
    def reset(self):
        """Resetar mtricas."""
        with self._lock:
            self.history.clear()
            self.total_stt_requests = 0
            self.successful_stt = 0
            self.total_tts_requests = 0
            self.total_listening_time = 0.0
            self.total_speaking_time = 0.0


class VADOptimizer:
    """Otimizador de Voice Activity Detection."""
    
    def __init__(self):
        self.noise_baseline = 300  # Baseline de rudo
        self.sensitivity = 1.0      # Multiplicador de sensibilidade
        self.adaptive_enabled = True
        self._lock = threading.Lock()
    
    def update_baseline(self, ambient_noise_level: int):
        """Atualizar baseline de rudo ambiental."""
        with self._lock:
            self.noise_baseline = int(self.noise_baseline * 0.7 + ambient_noise_level * 0.3)
    
    def get_threshold(self) -> float:
        """Obter threshold ajustado dinamicamente."""
        with self._lock:
            return self.noise_baseline * self.sensitivity
    
    def set_sensitivity(self, value: float):
        """Definir sensibilidade (0.5-2.0)."""
        with self._lock:
            self.sensitivity = max(0.5, min(2.0, value))
    
    def adjust_sensitivity(self, delta: float):
        """Ajustar sensibilidade relativamente."""
        with self._lock:
            self.sensitivity = max(0.5, min(2.0, self.sensitivity + delta))


class STSSystem:
    """
    Sistema unificado Speech-to-Speech.
    
    Features:
    - Orquestrao de STT, TTS, VAD
    - Mtricas e monitoramento
    - Adaptive Voice Activity Detection
    - Gerenciamento de estado
    - Callbacks para eventos
    - Recuperao automtica de erros
    """
    
    def __init__(self):
        # Componentes
        self.sts_engine = get_sts_engine()
        self.vad_optimizer = VADOptimizer()
        self.metrics = AudioMetrics()
        
        # Callbacks
        self.on_listening_start: Optional[Callable] = None
        self.on_listening_stop: Optional[Callable[[str], None]] = None
        self.on_speech_start: Optional[Callable] = None
        self.on_speech_end: Optional[Callable] = None
        self.on_speaking_start: Optional[Callable] = None
        self.on_speaking_end: Optional[Callable] = None
        self.on_error: Optional[Callable[[str], None]] = None
        
        # Estado
        self.is_listening = False
        self.is_speaking = False
        self._state_lock = threading.Lock()
        
        # Conectar callbacks do STS engine
        self._setup_sts_callbacks()
    
    def _setup_sts_callbacks(self):
        """Conectar callbacks internos do STS engine."""
        original_on_speech_end = getattr(self.sts_engine, 'on_speech_end', None)
        def wrapped_on_speech_end(text: str):
            self._record_user_speech(text)
            if callable(original_on_speech_end):
                original_on_speech_end(text)
            if callable(self.on_listening_stop):
                self.on_listening_stop(text)
        self.sts_engine.on_speech_end = wrapped_on_speech_end
        self.sts_engine.on_speech_start = self.on_speech_start
    
    def _record_user_speech(self, text: str):
        """Registrar fala do usurio."""
        self.metrics.record_stt(
            success=bool(text),
            duration=0,  # Aproximado
            text=text
        )
    
    def listen(
        self,
        timeout: Optional[float] = None,
        ui_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """
        Escutar entrada de voz.
        
        Args:
            timeout: Timeout em segundos
            ui_callback: Callback para atualizar UI
        
        Returns:
            Texto transcrito ou None
        """
        start_time = time.time()
        
        try:
            with self._state_lock:
                self.is_listening = True
            if callable(self.on_listening_start):
                self.on_listening_start()
            reset_listening()
            result = record_voice()
            duration = time.time() - start_time
            self.metrics.record_listening(duration)
            if result:
                self.metrics.record_stt(
                    success=True,
                    duration=duration,
                    text=result
                )
            return result
        except Exception as e:
            error_msg = f"Erro ao escutar: {str(e)}"
            if callable(self.on_error):
                self.on_error(error_msg)
            return None
        finally:
            with self._state_lock:
                self.is_listening = False
    
    def speak(
        self,
        text: str,
        ui=None,
        blocking: bool = False
    ) -> bool:
        """
        Falar texto usando TTS.
        
        Args:
            text: Texto a falar
            ui: UI para callbacks
            blocking: Esperar concluso
        
        Returns:
            True se sucesso
        """
        if not text or not text.strip():
            return False
        start_time = time.time()
        try:
            with self._state_lock:
                self.is_speaking = True
            if callable(self.on_speaking_start):
                self.on_speaking_start()
            streaming_speak(text, ui=ui, blocking=blocking)
            duration = time.time() - start_time
            self.metrics.record_tts(duration=duration, text=text)
            return True
        except Exception as e:
            error_msg = f"Erro ao falar: {str(e)}"
            if callable(self.on_error):
                self.on_error(error_msg)
            return False
        finally:
            with self._state_lock:
                self.is_speaking = False
            if callable(self.on_speaking_end):
                self.on_speaking_end()
    
    def stop_speaking(self):
        """Parar fala imediatamente."""
        stop_speaking()
        with self._state_lock:
            self.is_speaking = False
    
    def is_audio_active(self) -> bool:
        """Verificar se h udio ativo (escuta ou fala)."""
        with self._state_lock:
            return self.is_listening or self.is_speaking
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obter mtricas do sistema."""
        return {
            "audio_metrics": self.metrics.get_stats(),
            "state": {
                "is_listening": self.is_listening,
                "is_speaking": self.is_speaking
            }
        }
    
    def get_recent_activity(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obter atividade recente."""
        return self.metrics.get_history(limit=limit)
    
    def adjust_vad_sensitivity(self, delta: float):
        """Ajustar sensibilidade VAD."""
        self.vad_optimizer.adjust_sensitivity(delta)
    
    def reset_metrics(self):
        """Resetar mtricas."""
        self.metrics.reset()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Obter status de sade do sistema."""
        stats = self.metrics.get_stats()
        health_score = 100
        if stats["total_stt_requests"] > 0 and stats["stt_success_rate"] < 80:
            health_score -= 20
        return {
            "health_score": health_score,
            "status": "healthy" if health_score >= 80 else "degraded",
            "metrics": stats,
            "timestamp": datetime.now().isoformat()
        }


# Singleton global
_sts_system: Optional[STSSystem] = None


def get_sts_system() -> STSSystem:
    """Obter instncia do sistema STS."""
    global _sts_system
    
    if _sts_system is None:
        _sts_system = STSSystem()
    
    return _sts_system


def listen_with_sts(timeout: Optional[float] = None) -> Optional[str]:
    """Helper function para escuta rpida."""
    system = get_sts_system()
    return system.listen(timeout=timeout)


def speak_with_sts(text: str, ui=None, blocking: bool = False) -> bool:
    """Helper function para fala rpida."""
    system = get_sts_system()
    return system.speak(text, ui=ui, blocking=blocking)
