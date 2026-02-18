# vision/vision_system.py
"""
Vision System - Unified Visual Processing Engine
=================================================
Wrapper inteligente que gerencia todas as anlises de tela
com caching, mtricas, e fallbacks.

Mantm os modelos existentes (screen_vision.py, visual_navigator.py)
sem modificao e adiciona camada superior.
"""

import os
import json
import time
import threading
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta
import pyautogui
from dotenv import load_dotenv

load_dotenv()

# Import dos modelos existentes (sem modificao)
from actions.screen_vision import capture_and_analyze_screen
from actions.visual_navigator import visual_navigator


class VisionCache:
    """Cache inteligente de anlises visuais."""
    
    def __init__(self, ttl_seconds: int = 30):
        self.cache = {}
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Obter valor do cache se ainda vlido."""
        with self._lock:
            if key not in self.cache:
                return None
            
            entry = self.cache[key]
            age = time.time() - entry["timestamp"]
            
            if age > self.ttl_seconds:
                del self.cache[key]
                return None
            
            return entry["data"]
    
    def set(self, key: str, data: Dict[str, Any]):
        """Armazenar no cache."""
        with self._lock:
            self.cache[key] = {
                "data": data,
                "timestamp": time.time()
            }
    
    def clear(self):
        """Limpar cache."""
        with self._lock:
            self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatsticas do cache."""
        with self._lock:
            return {
                "entries": len(self.cache),
                "size_bytes": sum(len(str(v)) for v in self.cache.values())
            }


class VisionMetrics:
    """Rastreador de mtricas do sistema de viso."""
    
    def __init__(self):
        self.total_analyses = 0
        self.successful_analyses = 0
        self.failed_analyses = 0
        self.total_time_seconds = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self._lock = threading.Lock()
    
    def record_analysis(self, success: bool, duration: float):
        """Registrar anlise."""
        with self._lock:
            self.total_analyses += 1
            self.total_time_seconds += duration
            
            if success:
                self.successful_analyses += 1
            else:
                self.failed_analyses += 1
    
    def record_cache_hit(self):
        """Registrar hit de cache."""
        with self._lock:
            self.cache_hits += 1
    
    def record_cache_miss(self):
        """Registrar miss de cache."""
        with self._lock:
            self.cache_misses += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatsticas completas."""
        with self._lock:
            total = self.total_analyses
            if total == 0:
                return {
                    "total_analyses": 0,
                    "success_rate": 0,
                    "avg_time_seconds": 0,
                    "cache_hit_rate": 0
                }
            
            cache_total = self.cache_hits + self.cache_misses
            
            return {
                "total_analyses": total,
                "successful": self.successful_analyses,
                "failed": self.failed_analyses,
                "success_rate": (self.successful_analyses / total) * 100,
                "avg_time_seconds": self.total_time_seconds / total,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_rate": (self.cache_hits / cache_total * 100) if cache_total > 0 else 0
            }
    
    def reset(self):
        """Resetar mtricas."""
        with self._lock:
            self.total_analyses = 0
            self.successful_analyses = 0
            self.failed_analyses = 0
            self.total_time_seconds = 0
            self.cache_hits = 0
            self.cache_misses = 0


class VisionSystem:
    """
    Sistema unificado de viso.
    
    Features:
    - Cache inteligente de anlises
    - Mtricas e monitoramento
    - Fallbacks automticos
    - Integrao com memria
    - Suporte a callbacks
    """
    
    def __init__(self, enable_cache: bool = True, cache_ttl: int = 30):
        self.cache_enabled = enable_cache
        self.cache = VisionCache(ttl_seconds=cache_ttl) if enable_cache else None
        self.metrics = VisionMetrics()
        
        # Callbacks
        self.on_analysis_start: Optional[Callable] = None
        self.on_analysis_complete: Optional[Callable] = None
        self.on_analysis_error: Optional[Callable] = None
        
        # Estado
        self._last_screen_hash = None
        self._analysis_in_progress = False
        self._lock = threading.Lock()
    
    def _get_screen_hash(self) -> str:
        """Obter hash da tela atual para deteco de mudanas."""
        try:
            import hashlib
            screenshot = pyautogui.screenshot()
            screenshot.thumbnail((256, 256))  # Reduzir tamanho para hash
            
            # Converter para bytes e calcular hash
            img_bytes = screenshot.tobytes()
            return hashlib.md5(img_bytes).hexdigest()
        except:
            return None
    
    def analyze_screen(
        self,
        question: str = "",
        use_cache: bool = True,
        player=None,
        session_memory=None
    ) -> Optional[Dict[str, Any]]:
        """
        Analisar tela com cache inteligente.
        
        Args:
            question: Pergunta especfica sobre a tela
            use_cache: Usar cache se disponvel
            player: Player UI para log
            session_memory: Memria de sesso para armazenar contexto
        
        Returns:
            Dict com anlise ou None se falhar
        """
        start_time = time.time()
        cache_key = f"screen_analysis:{question}:{self._get_screen_hash()}"
        
        # Verificar cache
        if use_cache and self.cache_enabled:
            cached = self.cache.get(cache_key)
            if cached:
                self.metrics.record_cache_hit()
                if self.on_analysis_complete:
                    self.on_analysis_complete(cached, from_cache=True)
                return cached
            self.metrics.record_cache_miss()
        
        # Callback de incio
        if self.on_analysis_start:
            self.on_analysis_start(question)
        
        try:
            with self._lock:
                self._analysis_in_progress = True
            
            # Usar funo existente
            description = capture_and_analyze_screen(
                player=player,
                session_memory=session_memory,
                user_question=question
            )
            
            duration = time.time() - start_time
            self.metrics.record_analysis(success=True, duration=duration)
            
            result = {
                "success": True,
                "description": description,
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": duration,
                "question": question
            }
            
            # Cache se habilitado
            if self.cache_enabled:
                self.cache.set(cache_key, result)
            
            if self.on_analysis_complete:
                self.on_analysis_complete(result, from_cache=False)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_analysis(success=False, duration=duration)
            
            error_result = {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": duration
            }
            
            if self.on_analysis_error:
                self.on_analysis_error(error_result)
            
            return error_result
        
        finally:
            with self._lock:
                self._analysis_in_progress = False
    
    def navigate_to_target(
        self,
        target: str,
        action_type: str = "move",
        response: str = None,
        player=None,
        session_memory=None,
        max_retries: int = 5
    ) -> bool:
        """
        Navegar visualmente para um alvo na tela.
        
        Args:
            target: Descrio do elemento a encontrar
            action_type: Tipo de ao (move, click, double_click)
            response: Resposta da IA para ler
            player: Player UI para log
            session_memory: Memria de sesso
            max_retries: Tentativas mximas
        
        Returns:
            True se sucesso, False se falhar
        """
        start_time = time.time()
        
        try:
            if self.on_analysis_start:
                self.on_analysis_start(f"Navegao para: {target}")
            
            # Usar funo existente
            parameters = {
                "target": target,
                "action_type": action_type
            }
            
            success = visual_navigator(
                parameters=parameters,
                response=response,
                player=player,
                session_memory=session_memory
            )
            
            duration = time.time() - start_time
            self.metrics.record_analysis(success=success, duration=duration)
            
            if self.on_analysis_complete:
                self.on_analysis_complete({
                    "target": target,
                    "success": success,
                    "duration_seconds": duration
                }, from_cache=False)
            
            return success
            
        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_analysis(success=False, duration=duration)
            
            if self.on_analysis_error:
                self.on_analysis_error({
                    "target": target,
                    "error": str(e),
                    "duration_seconds": duration
                })
            
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obter mtricas do sistema."""
        return {
            "vision_metrics": self.metrics.get_stats(),
            "cache_stats": self.cache.get_stats() if self.cache_enabled else None,
            "cache_enabled": self.cache_enabled
        }
    
    def clear_cache(self):
        """Limpar cache."""
        if self.cache_enabled:
            self.cache.clear()
    
    def reset_metrics(self):
        """Resetar mtricas."""
        self.metrics.reset()


# Singleton global
_vision_system: Optional[VisionSystem] = None


def get_vision_system(enable_cache: bool = True) -> VisionSystem:
    """Obter instncia do sistema de viso."""
    global _vision_system
    
    if _vision_system is None:
        _vision_system = VisionSystem(enable_cache=enable_cache)
    
    return _vision_system


def analyze_screen_with_vision(
    question: str = "",
    use_cache: bool = True,
    player=None,
    session_memory=None
) -> Optional[Dict[str, Any]]:
    """Helper function para anlise rpida."""
    vision = get_vision_system()
    return vision.analyze_screen(
        question=question,
        use_cache=use_cache,
        player=player,
        session_memory=session_memory
    )


def navigate_with_vision(
    target: str,
    action_type: str = "move",
    response: str = None,
    player=None,
    session_memory=None
) -> bool:
    """Helper function para navegao rpida."""
    vision = get_vision_system()
    return vision.navigate_to_target(
        target=target,
        action_type=action_type,
        response=response,
        player=player,
        session_memory=session_memory
    )
