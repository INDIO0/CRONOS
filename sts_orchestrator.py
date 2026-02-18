"""
Crono STS Orchestrator
========================
Full-Duplex Speech-to-Speech Orchestrator
Inspired by Moshi's real-time dialogue architecture.

Features:
- Full-duplex: Listen while speaking
- Natural conversation flow
- Organized task orchestration pipeline
"""

import os
import sys
import asyncio
import threading
import uuid
from collections import deque
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass
from enum import Enum

# Ensure correct working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.append(BASE_DIR)

from sts_engine import STSEngine, get_sts_engine
from streaming_tts import streaming_speak, stop_speaking, set_callbacks as set_tts_callbacks
from llm import get_llm_output, detect_intent_by_keywords
from core.plan_schema import normalize_plan, validate_plan
from core.risk_policy import assess_risk, requires_confirmation
from emotion_system import get_proactive_commentator
from text_selector import get_text_reader
from system_monitor import SystemMonitor
try:
    import keyboard as kb
except Exception:
    kb = None


# Import all actions
from actions.open_app import open_app
from actions.close_app import close_app
from actions.weather_report import weather_action
from actions.screen_vision import capture_and_analyze_screen
from actions.type_text import type_text_action
from actions.file_operations import file_operations
from actions.project_manager import project_manager
from actions.system_command import system_command_action
from actions.screen_control import screen_controller
from actions.keyboard_control import press_key_action
from actions.open_website import open_website_action
from actions.media_player import play_playlist_action
from actions.visual_navigator import visual_navigator
from actions.timer import set_timer_action
from actions.calendar import schedule_calendar_action
from actions.ada_web_agent import get_ada_web_agent

from monitor_manager import setup_secondary_monitor_mode, move_window_to_primary, move_cmd_to_primary, MonitorManager
from file_manager import get_file_manager
try:
    from core.autonomous_memory import AutonomousMemoryManager
except Exception:
    AutonomousMemoryManager = None
from user_vocabulary import correct_text, maybe_handle_vocab_command, import_variants_block

try:
    from core.memory_store import MemoryStore
except Exception:
    MemoryStore = None


class CommandType(Enum):
    """Tipos de comandos especiais"""
    SHUTDOWN = "shutdown"
    RESTART = "restart"
    INTERRUPT = "interrupt"
    STANDBY_ON = "standby_on"
    STANDBY_OFF = "standby_off"
    SNOOZE_ON = "snooze_on"
    SNOOZE_OFF = "snooze_off"
    READ_SELECTED = "read_selected"
    TYPING_MODE_ON = "typing_mode_on"
    TYPING_MODE_OFF = "typing_mode_off"
    VOCAB_IMPORT = "vocab_import"
    NORMAL = "normal"


@dataclass
class CommandResult:
    """Resultado da anlise de comando"""
    command_type: CommandType
    should_process: bool
    message: Optional[str] = None
    selected_text: Optional[str] = None


class _NullSQLite:
    def health_check(self) -> bool:
        return True

    def _initialize_database(self) -> None:
        return None


class _NullMemory:
    def __init__(self):
        self.sqlite = _NullSQLite()

    def start_session(self, *args, **kwargs):
        return "null-session"

    def add_message(self, *args, **kwargs):
        return None

    def get_active_context(self):
        return None, None

    def get_profile(self):
        return {}

    def set_profile_field(self, *args, **kwargs):
        return None

    def update_profile_from_memory_update(self, *args, **kwargs):
        return None

    def get_recent_messages(self, *args, **kwargs):
        return []

    def format_recent_summaries(self, *args, **kwargs):
        return ""

    def prune_summaries(self, *args, **kwargs):
        return None

    def prune_old_messages(self, *args, **kwargs):
        return None

    def prune_expired_notes(self, *args, **kwargs):
        return None

    def vacuum(self, *args, **kwargs):
        return None

    def search_notes(self, *args, **kwargs):
        return []

    def get_recent_notes(self, *args, **kwargs):
        return []

    def add_remember_note(self, *args, **kwargs):
        return None


class _NullSessionMemory:
    def __init__(self):
        self.pending_intent = None
        self.intent_confidence = 0.0
        self.parameters = {}
        self.current_question = None
        self.pending_plan = None
        self.pending_step_index = 0
        self.awaiting_confirmation = False
        self.confirmation_step_id = None
        self.confirmation_attempts = 0
        self.open_app = None
        self.active_project = None
        self.last_user_text = None
        self.last_ai_response = None
        self.last_search = None
        self.last_timer_seconds = None
        self.last_timer_label = None
        self.last_timer_set_at = None
        self.last_timer_end_at = None
        self.active_timers = []

    def get_current_question(self):
        return self.current_question

    def update_parameters(self, new_params: dict | None = None):
        if isinstance(new_params, dict):
            for k, v in new_params.items():
                if v not in (None, ""):
                    self.parameters[k] = v
        return None

    def get_parameter(self, key: str):
        return self.parameters.get(key, "")

    def set_current_question(self, param_name: str):
        self.current_question = param_name

    def clear_current_question(self):
        self.current_question = None
        return None

    def get_last_user_text(self):
        return self.last_user_text

    def set_last_user_text(self, *args, **kwargs):
        if args:
            self.last_user_text = args[0]
        return None

    def set_last_ai_response(self, *args, **kwargs):
        if args:
            self.last_ai_response = args[0]
        return None

    def get_last_ai_response(self):
        return self.last_ai_response

    def get_history_for_prompt(self):
        return []

    def get_context_summary(self):
        return {}

    def get_action_history(self, *args, **kwargs):
        return []

    def get_last_search(self):
        return self.last_search

    def set_last_timer(self, seconds: int | None, label: str | None = None):
        self.last_timer_seconds = seconds
        self.last_timer_label = label
        return None

    def set_last_timer_times(self, start_ts: float | None, end_ts: float | None):
        self.last_timer_set_at = start_ts
        self.last_timer_end_at = end_ts
        return None

    def register_timer(self, timer_id: str, title: str, duration_seconds: int, cancel_event):
        import time
        created_at = time.time()
        duration = int(duration_seconds)
        self.active_timers.append(
            {
                "id": timer_id,
                "title": title,
                "duration": duration,
                "created_at": created_at,
                "end_at": created_at + max(0, duration),
                "cancel_event": cancel_event,
            }
        )
        return None

    def complete_timer(self, timer_id: str, canceled: bool = False):
        self.active_timers = [t for t in self.active_timers if t.get("id") != timer_id]
        return None

    def cancel_last_timer(self) -> bool:
        if not self.active_timers:
            return False
        timer = self.active_timers.pop()
        ev = timer.get("cancel_event")
        try:
            if ev:
                ev.set()
        except Exception:
            pass
        return True

    def cancel_all_timers(self) -> int:
        count = 0
        for timer in list(self.active_timers):
            ev = timer.get("cancel_event")
            try:
                if ev:
                    ev.set()
            except Exception:
                pass
            count += 1
        self.active_timers = []
        return count

    def get_visual_context(self):
        return None

    def has_pending_intent(self):
        return False

    def get_parameters(self):
        return self.parameters.copy()

    def get_active_project(self):
        return self.active_project

    def set_active_project(self, name, path, context):
        self.active_project = {"name": name, "path": path, "context": context}
        return None

    def clear_active_project(self):
        self.active_project = None
        return None

    def set_pending_plan(self, *args, **kwargs):
        return None

    def get_pending_plan(self):
        return None

    def clear_pending_plan(self):
        return None

    def set_confirmation(self, *args, **kwargs):
        return None

    def clear_confirmation(self):
        return None

    def record_action(self, *args, **kwargs):
        return None

    def set_open_app(self, *args, **kwargs):
        if args:
            self.open_app = args[0]
        return None

    def add_visual_context(self, *args, **kwargs):
        return None

    def set_last_search(self, *args, **kwargs):
        if len(args) >= 2:
            self.last_search = {"query": args[0], "answer": args[1]}
        return None

    def clear_pending_intent(self):
        self.pending_intent = None
        self.parameters = {}
        return None


class _NullMem0:
    def extract_memories(self, *args, **kwargs):
        return []

    def add_memory(self, *args, **kwargs):
        return None

    def search(self, *args, **kwargs):
        return []


class CommandProcessor:
    """Processador de comandos especiais"""
    
    SHUTDOWN_COMMANDS = ["desligar", "desliga", "quit", "exit", "encerrar sistema"]
    RESTART_COMMANDS = ["reiniciar", "restart", "reboot", "reinicie"]
    INTERRUPT_COMMANDS = ["parar", "pare", "silncio", "mudo", "cancelar", "chega"]
    STANDBY_ON_COMMANDS = [
        "standby", "stand-by", "modo standby", "modo stand-by",
        "pausar", "pause", "pausa", "dormir", "descansar"
    ]
    STANDBY_OFF_COMMANDS = [
        "voltar", "retome", "acordar", "acorde", "despausar",
        "sair do standby", "sair do stand-by", "modo normal", "continuar"
    ]
    SNOOZE_ON_COMMANDS = [
        "soneca", "modo soneca", "cochilar"
    ]
    SNOOZE_OFF_COMMANDS = [
        "acordar", "acorde", "retomar", "retome", "voltar", "modo normal", "continuar"
    ]
    READ_COMMANDS = [
        "leia", "leia isso", "leia o texto", "leia o selecionado",
        "leia esse texto", "ler",
        "traduz", "traduzir", "traduza", "traduza isso",
        "analisa", "analisar", "analise", "analise isso",
        "resuma", "resumir", "resumo", "resumo disso",
        "explica", "explicar", "explique", "explique isso"
    ]
    TYPING_MODE_ON_COMMANDS = [
        "ativar modo escrito", "ativar modo de escrita", "ativar modo de digitacao", "ativar modo digitacao",
        "entrar no modo escrito", "entrar no modo de escrita", "modo escrito", "modo de escrita",
        "modo digitacao", "modo de digitacao", "ligar modo escrito", "ligar modo de escrita"
    ]
    TYPING_MODE_OFF_COMMANDS = [
        "sair do modo escrita", "sair do modo escrito", "sair do modo de escrita",
        "desativar modo escrito", "desativar modo de escrita", "desativar o modo escrito", "desativar o modo de escrita",
        "desligar modo escrito", "desligar modo de escrita", "desligar o modo escrito", "desligar o modo de escrita",
        "parar modo escrito", "parar modo de escrita"
    ]
    VOCAB_IMPORT_COMMANDS = [
        "corrigir vocabulario", "corrigir vocabulrio",
        "corrige vocabulario", "corrige vocabulrio",
        "corrija vocabulario", "corrija vocabulrio",
        "corrige esse vocabulario", "corrige esse vocabulrio",
        "atualizar vocabulario", "atualizar vocabulrio",
        "atualize vocabulario", "atualize vocabulrio",
        "adicionar vocabulario", "adicionar vocabulrio",
        "adicione vocabulario", "adicione vocabulrio",
        "adiciona vocabulario", "adiciona vocabulrio",
        "importar vocabulario", "importar vocabulrio",
        "importe vocabulario", "importe vocabulrio",
        "importa vocabulario", "importa vocabulrio"
    ]
    
    def __init__(self, text_reader):
        self.text_reader = text_reader

    def _normalize_text(self, text: str) -> str:
        import unicodedata
        if not text:
            return ""
        text = text.lower().strip()
        return "".join(
            ch for ch in unicodedata.normalize("NFD", text)
            if unicodedata.category(ch) != "Mn"
        )
    def _contains_command(self, text_lower: str, commands: list[str]) -> bool:
        if not text_lower:
            return False
        import re
        words = set(re.findall(r"\b\w+\b", text_lower))
        for cmd in commands:
            cmd_norm = self._normalize_text(cmd)
            if not cmd_norm:
                continue
            # Use substring for phrases or non-word tokens (e.g., stand-by)
            if " " in cmd_norm or re.search(r"[^\w]", cmd_norm):
                if cmd_norm in text_lower:
                    return True
            else:
                if cmd_norm in words:
                    return True
        return False


    
    def analyze(self, text: str) -> CommandResult:
        """Analisa o texto e determina o tipo de comando"""
        text_lower = self._normalize_text(text)
        
        # Verificar comandos de desligamento
        if self._contains_command(text_lower, self.SHUTDOWN_COMMANDS):
            return CommandResult(
                command_type=CommandType.SHUTDOWN,
                should_process=False,
                message="Comando de desligamento detectado"
            )
        
        # Verificar comandos de reincio
        if self._contains_command(text_lower, self.RESTART_COMMANDS):
            return CommandResult(
                command_type=CommandType.RESTART,
                should_process=False,
                message="Comando de reincio detectado"
            )
        
        # Verificar comandos de interrupo
        if self._contains_command(text_lower, self.INTERRUPT_COMMANDS):
            return CommandResult(
                command_type=CommandType.INTERRUPT,
                should_process=False,
                message="Comando de interrupo detectado"
            )

        if self._contains_command(text_lower, self.STANDBY_ON_COMMANDS):
            return CommandResult(
                command_type=CommandType.STANDBY_ON,
                should_process=False,
                message="Modo standby ativado"
            )

        if self._contains_command(text_lower, self.STANDBY_OFF_COMMANDS):
            return CommandResult(
                command_type=CommandType.STANDBY_OFF,
                should_process=False,
                message="Modo standby desativado"
            )

        if self._contains_command(text_lower, self.SNOOZE_ON_COMMANDS):
            return CommandResult(
                command_type=CommandType.SNOOZE_ON,
                should_process=False,
                message="Modo soneca ativado"
            )

        if self._contains_command(text_lower, self.SNOOZE_OFF_COMMANDS):
            return CommandResult(
                command_type=CommandType.SNOOZE_OFF,
                should_process=False,
                message="Modo soneca desativado"
            )

        if self._matches_typing_mode_off(text_lower):
            return CommandResult(
                command_type=CommandType.TYPING_MODE_OFF,
                should_process=False,
                message="Modo escrito desativado"
            )

        if self._matches_typing_mode_on(text_lower):
            return CommandResult(
                command_type=CommandType.TYPING_MODE_ON,
                should_process=False,
                message="Modo escrito ativado"
            )

        if (
            any(self._normalize_text(cmd) in text_lower for cmd in self.VOCAB_IMPORT_COMMANDS)
            or (
                "vocabulario" in text_lower
                and any(
                    v in text_lower
                    for v in [
                        "corrigir", "corrige", "corrija",
                        "atualizar", "atualize",
                        "adicionar", "adicione", "adiciona",
                        "importar", "importe", "importa"
                    ]
                )
            )
        ):
            selected_text = self.text_reader.get_last_selected()
            if selected_text:
                return CommandResult(
                    command_type=CommandType.VOCAB_IMPORT,
                    should_process=True,
                    selected_text=selected_text
                )
            return CommandResult(
                command_type=CommandType.VOCAB_IMPORT,
                should_process=False,
                message="Nenhum texto copiado"
            )
        
        # Verificar comandos de leitura de texto selecionado
        if self._matches_read_command(text_lower):
            selected_text = self.text_reader.get_last_selected()
            if selected_text:
                return CommandResult(
                    command_type=CommandType.READ_SELECTED,
                    should_process=True,
                    selected_text=selected_text
                )
            else:
                return CommandResult(
                    command_type=CommandType.READ_SELECTED,
                    should_process=False,
                    message="Nenhum texto copiado"
                )
        
        # Comando normal
        return CommandResult(
            command_type=CommandType.NORMAL,
            should_process=True
        )

    def _matches_typing_mode_off(self, text_lower: str) -> bool:
        if not text_lower:
            return False
        if any(self._normalize_text(cmd) in text_lower for cmd in self.TYPING_MODE_OFF_COMMANDS):
            return True
        # Catch phrases like "desativar o modo escrito"
        if "modo escrito" in text_lower and any(k in text_lower for k in ["desativ", "deslig", "sair"]):
            return True
        if "modo de escrita" in text_lower and any(k in text_lower for k in ["desativ", "deslig", "sair"]):
            return True
        return False

    def _matches_typing_mode_on(self, text_lower: str) -> bool:
        if not text_lower:
            return False
        if any(self._normalize_text(cmd) in text_lower for cmd in self.TYPING_MODE_ON_COMMANDS):
            return True
        if "modo escrito" in text_lower and any(k in text_lower for k in ["ativ", "ligar", "entrar"]):
            return True
        if "modo de escrita" in text_lower and any(k in text_lower for k in ["ativ", "ligar", "entrar"]):
            return True
        return False

    def _matches_read_command(self, text_lower: str) -> bool:
        """Evita falsos positivos em comandos de leitura"""
        if not text_lower:
            return False

        # Verbos amplos (explicar, resumir, analisar, traduzir) sem contexto de texto
        # devem cair no fluxo normal de conversa/conhecimento.
        broad_read_stems = ["explic", "resum", "analis", "traduz"]
        text_context_markers = ["texto", "isso", "selecionado", "copiado", "trecho", "paragrafo", "pargrafo"]
        if any(stem in text_lower for stem in broad_read_stems):
            if not any(marker in text_lower for marker in text_context_markers):
                return False

        words = text_lower.split()
        for cmd in self.READ_COMMANDS:
            cmd_norm = self._normalize_text(cmd)
            if not cmd_norm:
                continue
            if len(cmd_norm) <= 3:
                if cmd_norm in words:
                    return True
            else:
                if cmd_norm in text_lower:
                    return True
        return False


class TaskOrchestrator:
    """Orquestrador de tarefas com pipeline organizado"""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
    
    async def execute_pipeline(self, text: str) -> bool:
        """Executa o pipeline completo de processamento"""
        try:
            # Fase 1: Pr-processamento
            if not await self._preprocess(text):
                return False
            
            # Fase 2: Validao
            if not await self._validate():
                return False
            
            # Fase 3: Preparao de contexto
            context = await self._prepare_context()
            
            # Fase 4: Processamento LLM
            llm_output = await self._process_with_llm(context)
            if not llm_output:
                return False
            
            # Fase 5: Execuo de aes
            await self._execute_actions(llm_output, text)
            
            # Fase 6: Ps-processamento
            await self._postprocess()
            
            return True
            
        except Exception as e:
            self.orchestrator._log(f" Erro no pipeline: {e}")
            return False
    
    async def _preprocess(self, text: str) -> bool:
        """Fase 1: Pr-processamento da entrada"""
        self.orchestrator.last_interaction_time = asyncio.get_event_loop().time()
        
        self.orchestrator.last_user_text = text
        return True
    
    async def _validate(self) -> bool:
        """Fase 2: Validao de pr-condies"""
        # Verificar interrupo
        if self.orchestrator.sts_engine.interrupt_requested:
            self.orchestrator.sts_engine.interrupt_requested = False
            return False
        
        return True
    
    async def _prepare_context(self) -> dict:
        """Fase 3: Preparao do contexto para o LLM"""
        return {}
    
    async def _process_with_llm(self, context: dict) -> Optional[dict]:
        """Fase 4: Processamento com LLM"""
        user_text = self.orchestrator.last_user_text or ""
        if self.orchestrator._game_context:
            user_text = (
                "Contexto: o usuario esta falando sobre um videogame "
                "(ex: Need for Speed). Nao dÃª conselhos do mundo real. "
                "Responda no contexto do jogo.\n"
                f"Pergunta: {user_text}"
            )
        
        try:
            self.orchestrator._log("Pensamento: analisando pedido...")
            llm_output = await asyncio.to_thread(
                get_llm_output,
                user_text=user_text,
                memory_block=self.orchestrator._build_memory_block(),
                include_reasoning=False,
                reasoning_format="hidden",
                reasoning_effort="low",
                allow_reasoning_hint=False,
                use_prompt_cache=self.orchestrator.use_prompt_cache,
                structured_outputs=False,
                use_tools=False,
                tool_choice=None,
            )
            
            # Verificar interrupo durante LLM
            if self.orchestrator.sts_engine.interrupt_requested:
                self.orchestrator.sts_engine.interrupt_requested = False
                return None
            try:
                self.orchestrator._log_thought_summary(llm_output)
            except Exception:
                pass
            return llm_output
            
        except Exception as e:
            self.orchestrator._log(f" Erro ao processar com LLM: {e}")
            return None
    
    async def _execute_actions(self, llm_output: dict, user_text: str):
        """Fase 5: Execuo das aes"""
        await self.orchestrator._process_llm_output(llm_output, user_text)
    
    async def _postprocess(self):
        """Fase 6: PÃ³s-processamento e limpeza"""
        return


class CronoSTSOrchestrator:
    """
    Full-Duplex STS Orchestrator for Crono
    Uses continuous VAD with echo cancellation for natural conversation.
    """
    
    def __init__(self, ui=None):
        self.ui = ui
        self.running = True
        self.last_user_text = None
        self.last_ai_response = None
        self.temp_memory = _NullSessionMemory()
        if MemoryStore:
            self.memory = MemoryStore(base_dir=BASE_DIR)
        else:
            self.memory = _NullMemory()
        if AutonomousMemoryManager:
            self.autonomous_memory = AutonomousMemoryManager(base_dir=BASE_DIR)
        else:
            self.autonomous_memory = None
        self.session_id = self.memory.start_session()
        self._recent_transcripts = deque(maxlen=8)

        # Initialize STS Engine

        self.sts_engine = get_sts_engine()

        # Initialize emotion system
        self.emotion_commentator = get_proactive_commentator()
        
        # Initialize text selection reader
        self.text_reader = get_text_reader()
        self.text_reader.on_text_copied = self._on_text_copied
        
        # Initialize file manager
        self.file_manager = get_file_manager()
        self.ada_web_agent = get_ada_web_agent()
        
        # Connect to TTS for echo cancellation
        from tts import set_sts_engine
        set_sts_engine(self.sts_engine)
        set_tts_callbacks(self._on_tts_start, self._on_tts_stop)
        
        self.sts_engine.on_speech_start = self._on_user_speech_start
        self.sts_engine.on_speech_end = self._on_user_speech_end
        self.sts_engine.on_interrupt = self._on_interrupt

        # Push-to-talk configuravel
        self._ptt_key = str(os.getenv("CRONO_PTT_KEY") or "insert").strip().lower()
        self._ptt_enabled = True
        self._ptt_is_down = False
        self._ptt_press_hook = None
        self._ptt_release_hook = None
        if kb:
            self._register_ptt_hooks()
        else:
            self._log(" Tecla PTT indisponivel (modulo 'keyboard' nao encontrado).")
            self._ptt_enabled = False


        if self.ui and hasattr(self.ui, "set_standby_callback"):
            self.ui.set_standby_callback(self.set_standby)
        if self.ui and hasattr(self.ui, "set_snooze_callback"):
            self.ui.set_snooze_callback(self.set_snooze)
        if self.ui and hasattr(self.ui, "set_ptt_callback"):
            self.ui.set_ptt_callback(self.set_ptt_enabled)
        if self.ui and hasattr(self.ui, "set_ptt_key_callback"):
            self.ui.set_ptt_key_callback(self.set_ptt_key)
        if self.ui and hasattr(self.ui, "set_knowledge_submit_callback"):
            self.ui.set_knowledge_submit_callback(self._handle_knowledge_submit)
        if self.ui and hasattr(self.ui, "set_message_submit_callback"):
            self.ui.set_message_submit_callback(self._handle_message_submit)
        if self.ui and hasattr(self.ui, "set_proactive_vision_callback"):
            self.ui.set_proactive_vision_callback(self.set_proactive_vision)
        if self.ui and hasattr(self.ui, "set_memory_panel_callbacks"):
            self.ui.set_memory_panel_callbacks(
                clear_short=self._clear_short_memory,
                clear_long=self._clear_long_memory,
                clear_visual=self._clear_visual_memory,
                refresh=self._refresh_memory_stats,
            )
            self._refresh_memory_stats()
        
        # Initialize command processor
        self.command_processor = CommandProcessor(self.text_reader)
        
        # Initialize task orchestrator
        self.task_orchestrator = TaskOrchestrator(self)
        
        # Proactivity settings
        self.last_interaction_time = asyncio.get_event_loop().time()
        self.typing_mode = False
        self.proactivity_check_interval = 30  # Check every 30s
        self.min_idle_time = 60  # 1 minute
        self.max_idle_time = 120  # 2 minutes
        self.proactive_vision_enabled = (os.getenv("CRONO_PROACTIVE_VISION") or "true").lower() in {"1", "true", "yes", "on"}
        self._proactivity_task = None
        self._status_task = None
        self._voice_active = False
        self._status_last = None
        self._status_interval = 0.5
        self._mic_meter_task = None
        self.standby = False
        self.snooze = False
        self._startup_alert_grace_sec = float(os.getenv("CRONO_STARTUP_ALERT_GRACE_SEC") or "90")
        self._startup_alert_until = 0.0
        self._has_user_interacted = False
        # Alertas proativos de sistema (CPU/RAM/Bateria/Rede) desativados por padrão.
        # O status continua disponível sob demanda via intent `system_status`.
        self._monitor_proactive_alerts = (os.getenv("CRONO_MONITOR_PROACTIVE_ALERTS") or "false").lower() in {"1", "true", "yes", "on"}
        self._monitor_alert_snooze_sec = float(os.getenv("CRONO_MONITOR_ALERT_SNOOZE_SEC") or "20")
        self._monitor_alert_snooze_until = 0.0
        self._game_context = False
        self.include_reasoning = (os.getenv("CRONO_INCLUDE_REASONING") or "true").lower() in {"1", "true", "yes", "on"}
        self.reasoning_format = os.getenv("CRONO_REASONING_FORMAT") or "parsed"
        self.reasoning_effort = os.getenv("CRONO_REASONING_EFFORT") or "high"
        self.use_prompt_cache = (os.getenv("CRONO_USE_PROMPT_CACHE") or "true").lower() in {"1", "true", "yes", "on"}
        self.structured_outputs = (os.getenv("CRONO_STRUCTURED_OUTPUTS") or "true").lower() in {"1", "true", "yes", "on"}
        self.use_tools = (os.getenv("CRONO_USE_TOOLS") or "true").lower() in {"1", "true", "yes", "on"}
        self.tool_choice = os.getenv("CRONO_TOOL_CHOICE") or "auto"
        # Desativa atalhos por keyword para evitar intents erradas (sempre pensar via LLM)
        self.use_keyword_intents = (os.getenv("CRONO_USE_KEYWORD_INTENTS") or "false").lower() in {"1", "true", "yes", "on"}
        self._system_monitor_task = None
        self.system_monitor = SystemMonitor()

        # Echo suppression (TTS -> STT loop guard)
        self._last_tts_text = ""
        self._last_tts_start = 0.0
        self._last_tts_end = 0.0
        self._tts_active = False
        self._last_interrupt_at = 0.0
        self._interrupt_cooldown_sec = 1.2

        # Debounce/buffer para reduzir chamadas ao LLM (voz)
        self._debounce_window = float(os.getenv("CRONO_LLM_DEBOUNCE_SEC") or "0.9")
        self._debounce_max_parts = int(os.getenv("CRONO_LLM_DEBOUNCE_MAX_PARTS") or "4")
        self._debounce_short_window = float(os.getenv("CRONO_LLM_DEBOUNCE_SHORT_SEC") or "1.6")
        self._voice_buffer_parts = []
        self._voice_debounce_task = None
        self._web_task = None
        self._apply_listening_mode()
        if self.ui and hasattr(self.ui, "set_proactive_vision_state"):
            self.ui.set_proactive_vision_state(self.proactive_vision_enabled)
        if self.ui and hasattr(self.ui, "set_ptt_state"):
            self.ui.set_ptt_state(self._ptt_enabled)
        if self.ui and hasattr(self.ui, "set_ptt_key"):
            self.ui.set_ptt_key(self._ptt_key)

        # First-use protocol (ask user name occasionally)
        self._awaiting_user_name = False
        self._last_name_prompt_time = 0.0
        self._name_prompt_cooldown = 180.0
        self._name_prompt_chance = 0.35
        
        # Processing queue
        self._processing_lock = asyncio.Lock()
        self._event_loop: asyncio.AbstractEventLoop = None
        
        # Action handlers mapping
        self.action_handlers = {
            "open_app": self._handle_open_app,
            "close_app": self._handle_close_app,
            "type_text": self._handle_type_text,
            "press_key": self._handle_press_key,
            "open_website": self._handle_open_website,
            "weather_report": self._handle_weather,
            "system_status": self._handle_system_status,
            "file_operation": self._handle_file_operation,
            "project_manager": self._handle_project,
            "describe_screen": self._handle_describe_screen,
            "play_media": self._handle_play_media,
            "visual_navigate": self._handle_visual_navigate,
            "control_screen": self._handle_screen_control,
            "remember_note": self._handle_remember_note,
            "clear_popups": self._handle_clear_popups,
            "chat": self._handle_chat,
            "create_directory": self._handle_create_directory,
            "scan_directory": self._handle_scan_directory,
            "list_directory": self._handle_list_directory,
            "get_file_info": self._handle_get_file_info,
            "system_command": self._handle_system_command,
            "set_timer": self._handle_set_timer,
            "cancel_timer": self._handle_cancel_timer,
            "schedule_calendar": self._handle_schedule_calendar,
            "search_web": self._handle_search_web,
            "fetch_web_content": self._handle_fetch_web_content,
            "memory_durable_fact": self._handle_memory_durable_fact,
            "search_personal_data": self._handle_search_personal_data,
            "graphic_art": self._handle_graphic_art,
            "load_skills": self._handle_load_skills,
            "multi_tool_use.parallel": self._handle_multi_tool_parallel,
        }
    
    def _log(self, message: str):
        """Log message to UI or console"""
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [LOG] {message}")

    def _log_thought_summary(self, llm_output: dict | None) -> None:
        """Log a safe, brief 'thought' summary without internal chain-of-thought."""
        if not isinstance(llm_output, dict):
            return
        if llm_output.get("needs_clarification"):
            q = llm_output.get("clarifying_question") or "Preciso de mais detalhes."
            self._log(f"Pensamento: precisa esclarecer -> {q}")
            return
        plan = llm_output.get("plan") or []
        response = llm_output.get("response") or ""
        if plan:
            intents = []
            for step in plan:
                if isinstance(step, dict):
                    intents.append(step.get("intent") or "")
            intents = [i for i in intents if i]
            if intents:
                self._log(f"Pensamento: executar intents -> {', '.join(intents)}")
            else:
                self._log("Pensamento: executar plano.")
            return
        if response:
            self._log("Pensamento: resposta direta (sem acao).")

    def _looks_like_direct_visual_answer(self, description: str) -> bool:
        if not description:
            return False
        d = description.strip()
        d_low = d.lower()
        if len(d) > 220:
            return False
        # Evita descriÃ§Ãµes genÃ©ricas de "tela/imagem"
        if any(x in d_low for x in ["a imagem mostra", "a tela mostra", "a imagem apresenta", "a tela apresenta"]):
            return False
        # Respostas diretas tendem a ter verbos de identificaÃ§Ã£o/valores
        if any(x in d_low for x in [" Ã© ", " sÃ£o ", " estÃ¡ ", " valor ", " total ", "Ã© um", "Ã© uma"]):
            return True
        if any(ch.isdigit() for ch in d):
            return True
        return False

    def _maybe_answer_timer_query(self, text: str) -> str | None:
        if not text:
            return None
        t = self.command_processor._normalize_text(text)
        if not t:
            return None
        if not any(k in t for k in ["timer", "timers", "temporizador", "temporizadores", "alarme", "alarmes", "cronometro"]):
            return None
        # Perguntas de status/tempo do timer
        if not any(k in t for k in ["tempo", "quanto", "qual", "quais", "resta", "falt", "ativo", "ativos", "tem", "que eu pedi", "aquele"]):
            return None
        wants_remaining = any(
            k in t for k in [
                "quanto falta", "falta quanto", "falta", "resta", "quanto tempo",
                "acabar", "terminar", "pra acabar", "para acabar"
            ]
        )
        timers = list(getattr(self.temp_memory, "active_timers", []) or [])
        if timers:
            import time
            now = time.time()
            def _fmt_remaining(seconds: int) -> str:
                seconds = max(0, int(seconds))
                mins = seconds // 60
                secs = seconds % 60
                if mins > 0:
                    base = f"{mins} minuto" + ("s" if mins != 1 else "")
                    if secs:
                        base += f" e {secs} segundo" + ("s" if secs != 1 else "")
                    return base
                return f"{secs} segundo" + ("s" if secs != 1 else "")

            if wants_remaining:
                if len(timers) == 1:
                    timer = timers[0]
                    title = str(timer.get("title") or "temporizador")
                    end_at = timer.get("end_at")
                    if end_at is None:
                        duration = int(timer.get("duration") or 0)
                        created_at = float(timer.get("created_at") or now)
                        end_at = created_at + max(0, duration)
                    remaining = max(0, int(float(end_at) - now))
                    return f"Faltam {_fmt_remaining(remaining)} para o timer '{title}'."

                lines = []
                for timer in timers[:3]:
                    title = str(timer.get("title") or "temporizador")
                    end_at = timer.get("end_at")
                    if end_at is None:
                        duration = int(timer.get("duration") or 0)
                        created_at = float(timer.get("created_at") or now)
                        end_at = created_at + max(0, duration)
                    remaining = max(0, int(float(end_at) - now))
                    lines.append(f"{title}: {_fmt_remaining(remaining)}")
                return f"Voce tem {len(timers)} timers ativos. Tempo restante: " + "; ".join(lines) + "."

            lines = []
            for timer in timers[:3]:
                title = str(timer.get("title") or "temporizador")
                duration = int(timer.get("duration") or 0)
                suffix = f"{duration // 60} min" if duration >= 60 else f"{duration}s"
                lines.append(f"{title} ({suffix})")
            if len(timers) == 1:
                return f"Voce tem 1 timer ativo: {lines[0]}."
            return f"Voce tem {len(timers)} timers ativos: " + ", ".join(lines) + "."
        end_ts = getattr(self.temp_memory, "last_timer_end_at", None)
        start_ts = getattr(self.temp_memory, "last_timer_set_at", None)
        seconds = getattr(self.temp_memory, "last_timer_seconds", None)
        label = getattr(self.temp_memory, "last_timer_label", None)
        if not end_ts or not seconds:
            return "Nao tenho nenhum timer ativo agora."
        import time
        now = time.time()
        remaining = int(end_ts - now)
        if remaining <= 0:
            return "O timer ja terminou."
        # FormataÃ§Ã£o simples PT-BR
        mins = remaining // 60
        secs = remaining % 60
        if mins > 0:
            suffix = f"{mins} minuto" + ("s" if mins != 1 else "")
            if secs:
                suffix += f" e {secs} segundo" + ("s" if secs != 1 else "")
        else:
            suffix = f"{secs} segundo" + ("s" if secs != 1 else "")
        if label:
            return f"Faltam {suffix} para o timer '{label}'."
        return f"Faltam {suffix} para o timer."
    
    def _on_text_copied(self, text: str):
        """Callback quando texto  copiado"""
        if not text or not text.strip():
            return
        
        text = text.strip()
        if len(text) < 2:
            return
        
        # Informar que texto foi copiado
        preview = text[:60] + "..." if len(text) > 60 else text
        self._log(f" Texto copiado: {preview}")
        self._log(f" Diga o que quer fazer com este texto (traduzir, analisar, resumir, etc)")
    
    def _on_user_speech_start(self):
        """Called when user starts speaking"""
        if self.standby:
            return
        self._log(" Ouvindo...")
        self._voice_active = True
        # Evita proatividade enquanto o usuÃ¡rio fala
        try:
            self.last_interaction_time = asyncio.get_event_loop().time()
        except Exception:
            pass
    
    def _on_user_speech_end(self, text: str):
        """Called when user finishes speaking with transcribed text"""
        if not text or not text.strip():
            self._voice_active = False
            return
        self._recent_transcripts.append(text.strip())

        # Debounce para reduzir chamadas ao LLM
        if self._event_loop:
            asyncio.run_coroutine_threadsafe(
                self._enqueue_voice_input(text),
                self._event_loop,
            )
        self._voice_active = False

    async def _enqueue_voice_input(self, text: str):
        """Bufferiza fragmentos de voz e envia como uma unica mensagem."""
        text = str(text or "").strip()
        if not text:
            return
        if self._debounce_window <= 0:
            await self._process_user_input(text)
            return

        # Aumenta janela para fragmentos curtos/incompletos
        short_tokens = len(text.split()) <= 3
        trailing = text.endswith("...") or text.endswith("â€¦")
        window = self._debounce_short_window if (short_tokens or trailing) else self._debounce_window

        self._voice_buffer_parts.append(text)
        if len(self._voice_buffer_parts) >= self._debounce_max_parts:
            await self._flush_voice_buffer()
            return

        if self._voice_debounce_task and not self._voice_debounce_task.done():
            self._voice_debounce_task.cancel()
        self._voice_debounce_task = asyncio.create_task(self._debounce_voice_flush(window))

    async def _debounce_voice_flush(self, window: float):
        try:
            await asyncio.sleep(window)
        except asyncio.CancelledError:
            return
        await self._flush_voice_buffer()

    async def _flush_voice_buffer(self):
        if not self._voice_buffer_parts:
            return
        merged = " ".join(self._voice_buffer_parts).strip()
        self._voice_buffer_parts = []
        if merged:
            await self._process_user_input(merged)

    def _on_ptt_down(self, _event=None):
        if not self._ptt_enabled:
            return
        if self.standby or self.snooze:
            return
        if self._ptt_is_down:
            return
        self._ptt_is_down = True
        self._apply_listening_mode()
        self._log(f" PTT: ouvindo ({self._ptt_key} pressionado)")

    def _on_ptt_up(self, _event=None):
        if not self._ptt_enabled:
            return
        if not self._ptt_is_down:
            return
        self._ptt_is_down = False
        self._apply_listening_mode()
        self._log(f" PTT: mudo ({self._ptt_key} liberado)")
    
    def _on_interrupt(self):
        """Called when user interrupts Crono"""
        import time
        now = time.time()
        if now - self._last_interrupt_at < self._interrupt_cooldown_sec:
            return
        self._last_interrupt_at = now
        # Evita falso-positivo quando nao ha fala de TTS ativa.
        if not (self._tts_active or self.sts_engine.is_speaking):
            return
        stop_speaking()
        self._log(" Interrupcao detectada!")

    def _interrupt_response(self, _text: str):
        """Handle interrupt intent from text command."""
        self._log(" Interrupcao solicitada pelo usuario")

    def _on_tts_start(self):
        """Called when TTS starts playing"""
        self._tts_active = True
        import time
        self._last_tts_start = time.time()
        self.sts_engine.set_speaking(True)

    def _on_tts_stop(self):
        """Called when TTS stops playing"""
        self._tts_active = False
        import time
        self._last_tts_end = time.time()
        self.sts_engine.set_speaking(False)
    

    def _is_confirmation_response(self, text: str) -> bool | None:
        """Return True for yes, False for no, None if unclear."""
        if not text:
            return None
        t = "".join(ch for ch in text.strip().lower() if ch.isalnum() or ch.isspace()).strip()
        yes = {"sim", "s", "confirmar", "pode", "ok", "okay", "pode sim"}
        no = {"nao", "n", "negativo", "cancela", "cancelar", "pare", "parar"}
        if t in yes:
            return True
        if t in no:
            return False
        # aceitar frases que contenham sim/nao
        if "sim" in t:
            return True
        if "nao" in t:
            return False
        return None

    def _mentions_assistant_name(self, text: str) -> bool:
        if not text:
            return False
        t = self.command_processor._normalize_text(text)
        if not t:
            return False
        return ("crono" in t) or ("cronos" in t)

    def _is_sleep_wake(self, text: str) -> bool:
        if not self._mentions_assistant_name(text):
            return False
        t = self.command_processor._normalize_text(text)
        if any(self.command_processor._normalize_text(cmd) in t for cmd in CommandProcessor.SNOOZE_OFF_COMMANDS):
            return True
        if any(self.command_processor._normalize_text(cmd) in t for cmd in CommandProcessor.STANDBY_OFF_COMMANDS):
            return True
        if "acordar" in t or "acorde" in t or "retomar" in t or "retome" in t or "voltar" in t:
            return True
        # Nome do assistente por si so ja pode acordar.
        return False

    async def _build_wake_reply(self, user_text: str) -> str:
        prompt = (
            "Responda em portugues-BR com UMA frase curta para acordar um assistente de voz. "
            "Tom: educado, levemente sarcastico, sem grosseria, sem emoji. "
            "Nao descreva regras, nao use listas.\n\n"
            f"Fala do usuario: {user_text}"
        )
        try:
            out = await asyncio.to_thread(
                get_llm_output,
                user_text=prompt,
                memory_block=self._build_memory_block(),
                include_reasoning=False,
                reasoning_format="hidden",
                reasoning_effort="low",
                allow_reasoning_hint=False,
                structured_outputs=False,
                use_tools=False,
                tool_choice=None,
            )
            msg = str((out or {}).get("response") or "").strip()
            if msg:
                return msg
        except Exception:
            pass
        return "Acordei. Pode mandar."

    def _mem0_ingest_user_text(self, text: str):
        if not text or not text.strip():
            return
        try:
            self._maybe_store_long_term(text)
        except Exception as e:
            self._log(f"Erro ao ingerir memoria longa: {e}")

    def _mem0_add_summary(self, user_text: str, ai_text: str):
        # Desativado para evitar poluir memoria longa com resumos automÃ¡ticos.
        return

    def _normalize_echo_text(self, text: str) -> str:
        import unicodedata
        if not text:
            return ""
        text = text.strip().lower()
        text = "".join(
            ch for ch in unicodedata.normalize("NFD", text)
            if unicodedata.category(ch) != "Mn"
        )
        text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
        return " ".join(text.split())

    def _is_probable_echo(self, text: str) -> bool:
        if not self._last_tts_text or not self._last_tts_end:
            return False
        import time
        now = time.time()
        if now - self._last_tts_end > 8.0:
            return False

        norm_in = self._normalize_echo_text(text)
        last_ai = ""
        try:
            last_ai = self.temp_memory.get_last_ai_response() or ""
        except Exception:
            last_ai = ""
        norm_tts = self._normalize_echo_text(self._last_tts_text)
        norm_ai = self._normalize_echo_text(last_ai)
        candidates = [c for c in [norm_tts, norm_ai] if c]
        if not norm_in or not candidates:
            return False
        # Avoid suppressing short user replies
        if len(norm_in) < 8 or len(norm_in.split()) < 3:
            return False
        for cand in candidates:
            if norm_in in cand or cand in norm_in:
                return True

        try:
            from difflib import SequenceMatcher
            for cand in candidates:
                ratio = SequenceMatcher(None, norm_in, cand).ratio()
                if ratio >= 0.78:
                    return True
            return False
        except Exception:
            return False

    def _is_short_noise(self, text: str) -> bool:
        if not text:
            return True
        t = text.strip().lower()
        if not t:
            return True
        if all(ch in ".!," for ch in t):
            return True
        fillers = {
            "que", "ah", "eh", "e", "hum", "hmm", "han", "ha", "tipo", "ta", "opa"
        }
        if t in fillers:
            return True
        if len(t) <= 1:
            return True
        if len(t) <= 2 and t not in {"oi", "olá", "ola", "ok", "sim", "nao", "não"} and not t.isdigit():
            return True
        return False


    def _detect_quick_intent(self, text: str) -> str | None:
        if not text:
            return None
        import unicodedata
        t = "".join(
            ch for ch in unicodedata.normalize("NFD", text.lower())
            if unicodedata.category(ch) != "Mn"
        )
        phrases = [
            "olha minha tela",
            "olha a minha tela",
            "olhe minha tela",
            "olhe a minha tela",
            "olha a tela",
            "olhe a tela",
            "ver minha tela",
            "ver a minha tela",
            "ver a tela",
            "ve minha tela",
            "ve a minha tela",
            "ve a tela",
            "mostra minha tela",
            "mostra a minha tela",
            "mostra a tela",
            "mostre minha tela",
            "mostre a minha tela",
            "mostre a tela",
            "descreve a tela",
            "descrever a tela",
            "analisa a tela",
            "analise a tela",
            "analisa minha tela",
            "analise minha tela",
            "olha meu monitor",
            "olha o monitor",
            "olhe meu monitor",
            "olhe o monitor",
        ]
        if any(p in t for p in phrases):
            return "describe_screen"
        return None

    def _normalize_game_terms(self, text: str) -> str:
        if not text:
            return ""
        t = text
        # Common STT mistakes
        t = t.replace("ned for speed", "need for speed")
        t = t.replace("need for spid", "need for speed")
        t = t.replace("need for spd", "need for speed")
        return t

    def _detect_game_context(self, text: str) -> bool:
        if not text:
            return False
        import unicodedata
        t = "".join(
            ch for ch in unicodedata.normalize("NFD", text.lower())
            if unicodedata.category(ch) != "Mn"
        )
        if "need for speed" in t or "nfs" in t:
            return True
        if "jogo" in t and any(k in t for k in ["corrida", "carro", "policia", "pneu", "pneus"]):
            return True
        return False

    def _normalize_personal_text(self, text: str) -> str:
        import unicodedata
        t = (text or "").lower().strip()
        t = "".join(
            ch for ch in unicodedata.normalize("NFD", t)
            if unicodedata.category(ch) != "Mn"
        )
        return t

    def _is_memory_intent(self, text: str) -> bool:
        t = self._normalize_personal_text(text)
        if not t:
            return False
        markers = [
            "lembra", "lembre", "lembrar", "lembrando", "lembranca", "lembranÃ§a",
            "recorda", "recorde", "recordar",
            "me lembra", "me lembre", "me recorda",
            "sobre aquele", "sobre aquilo", "sobre isso",
            "como eu disse", "como eu falei", "como combinamos", "como falamos",
            "ontem", "anteontem", "semana passada", "mes passado", "mÃªs passado",
            "projeto de ontem", "aquele projeto", "projeto passado", "projeto anterior",
            "aquilo que conversamos", "aquilo que falamos", "isso que falamos",
            "voce se lembra", "vocÃª se lembra", "voce lembra", "vocÃª lembra",
            "daquele", "daquela", "daquilo", "disso",
            "aquela conversa", "aquele papo", "aquele assunto",
        ]
        if any(m in t for m in markers):
            return True
        # Patterns like "abre aquele projeto" or "retoma aquele projeto"
        if "projeto" in t and any(k in t for k in ["aquele", "anterior", "ontem", "passado", "retoma", "retomar", "abrir", "abre"]):
            return True
        # Past reference + vague pronoun
        if any(k in t for k in ["ontem", "anteontem", "semana passada", "mes passado", "mÃªs passado"]) and any(
            p in t for p in ["aquilo", "isso", "aquele", "aquela", "daquilo", "disso"]
        ):
            return True
        return False

    def _clean_memory_query(self, text: str) -> str:
        if not text:
            return ""
        t = text.lower()
        for prefix in [
            "cronos,", "cronos", "por favor", "pfv", "pode", "me lembra", "me lembre",
            "lembra", "lembre", "lembrar", "voce lembra", "vocÃª lembra", "voce se lembra", "vocÃª se lembra",
            "recorda", "recorde", "recordar", "me recorda",
        ]:
            t = t.replace(prefix, "")
        for remove in ["abra", "abre", "abrir", "retoma", "retomar", "sobre", "aquele", "aquela", "isso", "aquilo", "daquele", "daquela", "daquilo", "disso"]:
            t = t.replace(remove, "")
        t = t.strip(" .,!:;")
        if len(t) < 3:
            return ""
        return t

    def _fmt_ts(self, ts: float | None) -> str:
        import datetime
        try:
            return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "data desconhecida"

    def _maybe_store_long_term(self, text: str) -> None:
        import re
        t = (text or "").strip()
        if not t:
            return
        # Explicit remember commands
        patterns = [
            r"^(lembre|lembra|memoriza|memorize|guarda|guarde|salva|salve|anota|anote)(:\\s+que)\\s+(.+)$",
            r"^lembre\\s+que\\s+(.+)$",
        ]
        for pat in patterns:
            m = re.search(pat, t, flags=re.IGNORECASE)
            if m:
                content = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else m.group(1).strip()
                if content:
                    self.memory.add_long_term(content, kind="note", source="voice")
                    self._refresh_memory_stats()
                return

    def _is_personal_query(self, text: str) -> bool:
        t = self._normalize_personal_text(text)
        if not t:
            return False
        markers = [
            "meu nome", "me chamo", "meu", "minha", "meus", "minhas",
            "qual e meu", "qual eh meu", "qual e minha", "qual eh minha",
            "o que eu", "o que eu gosto", "o que eu prefiro", "lembra de mim", "lembra do meu"
        ]
        return any(m in t for m in markers)

    def _maybe_show_personal_memory_hint(self, text: str) -> None:
        if not self.ui or not hasattr(self.ui, "show_popup"):
            return
        if not self._is_personal_query(text):
            return
        try:
            profile = self.memory.get_profile()
            if "meu nome" in self._normalize_personal_text(text) and profile.get("user_name"):
                self.ui.show_popup("Memoria", f"Nome: {profile.get('user_name')}")
                return
        except Exception:
            pass
        try:
            notes = self.memory.search_notes(text, limit=1)
            if notes:
                snippet = notes[0].get("note", "")
                if snippet:
                    self.ui.show_popup("Memoria", snippet[:140])
        except Exception:
            pass

    def _user_name_known(self) -> bool:
        try:
            profile = self.memory.get_profile()
            name = profile.get("user_name")
            return bool(name and str(name).strip())
        except Exception:
            return False

    def _extract_user_name(self, text: str) -> str:
        import re
        if not text:
            return ""
        t = text.strip()
        t = re.sub(r"^(meu nome e|meu nome \u00e9|eu sou|pode me chamar de|me chame de|chamo-me)\s+", "", t, flags=re.IGNORECASE)
        t = t.strip(" .,!:;")
        return t

    def _detect_name_declaration(self, text: str) -> str:
        import re
        if not text:
            return ""
        pattern = r"(meu nome e|meu nome \u00e9|eu sou|pode me chamar de|me chame de|chamo-me)\s+(.+)"
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            return ""
        name = m.group(2).strip()
        name = name.strip(" .,!:;")
        return name

    def _looks_like_path(self, text: str) -> bool:
        import re
        if not text:
            return False
        t = text.strip().strip('"').strip("' ")
        # Windows drive path or UNC path
        if re.match(r'^[a-zA-Z]:\\', t) or t.startswith('\\'):
            return True
        # Common path-like patterns
        if '\\' in t and len(t) < 260:
            return True
        if '/' in t and ('./' in t or '../' in t or t.startswith('/')):
            return True
        return False

    def _mentions_selected_text(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        markers = [
            'texto copiado', 'texto selecionado', 'texto que copiei',
            'texto que eu copiei', 'esse texto', 'este texto',
            'esse trecho', 'este trecho', 'selecionado', 'copiado'
        ]
        return any(m in t for m in markers)


    def _should_prompt_name(self) -> bool:
        # Desativado: nÃ£o perguntar nome automaticamente em inatividade.
        return False

    async def _handle_confirmation_response(self, text: str) -> bool:
        """
        Handle pending confirmation. Returns True if handled and consumed.
        """
        if not self.temp_memory.awaiting_confirmation:
            return False

        decision = self._is_confirmation_response(text)
        if decision is None:
            self._log(f"CONFIRMACAO_INDEFINIDA: '{text}'")
            self.temp_memory.confirmation_attempts += 1
            if self.temp_memory.confirmation_attempts >= 3:
                self._log("CONFIRMACAO_FALHOU_LIMITE")
                self.temp_memory.clear_confirmation()
                self.temp_memory.clear_pending_plan()
                self._speak("Entendido. Cancelando a ao.")
                return True
            self._speak("Preciso de uma confirmao clara: sim ou No.")
            return True

        if decision is False:
            self._log("CONFIRMACAO_NEGADA")
            self.temp_memory.clear_confirmation()
            self.temp_memory.clear_pending_plan()
            self._speak("Entendido. Cancelando a aÃ§Ã£o.")
            return True

        plan = self.temp_memory.get_pending_plan()
        step_index = self.temp_memory.pending_step_index
        step_id = self.temp_memory.confirmation_step_id
        self._log(f"CONFIRMACAO_OK: step_index={step_index} step_id={step_id}")
        self.temp_memory.clear_confirmation()

        if not plan or step_index >= len(plan.plan):
            self._log("SEM_ACAO_PENDENTE")
            self._speak("NÃ£o hÃ¡ nenhuma aÃ§Ã£o pendente.")
            self.temp_memory.clear_pending_plan()
            return True

        await self._execute_plan_steps(plan, start_index=step_index, skip_confirmation_step_id=step_id)
        return True
    async def run(self):
        """Main orchestration loop"""
        self._event_loop = asyncio.get_event_loop()
        self._startup_alert_until = self._event_loop.time() + max(0.0, self._startup_alert_grace_sec)
        
        self._log("Crono STS Online - Modo Full-Duplex Ativo")
        self._log("Dica: VocÃª pode me interromper a qualquer momento!")
        self._log("Dica: Selecione texto com o mouse para eu ler!")
        
        # Start the STS engine
        self.sts_engine.start()
        try:
            from startup_greeting import build_startup_greeting
            text = build_startup_greeting()
            if text:
                self._speak(text)
        except Exception as e:
            self._log(f"Falha ao executar saudacao inicial: {e}")
        
        # Start text selection reader
        self.text_reader.start_monitoring()
        
        # Start proactivity monitor
        self._proactivity_task = asyncio.create_task(self._proactivity_loop())
        self._status_task = asyncio.create_task(self._status_loop())
        self._mic_meter_task = asyncio.create_task(self._mic_meter_loop())
        self._system_monitor_task = asyncio.create_task(self._system_monitor_loop())
        
        try:
            while self.running:
                await asyncio.sleep(1.0)
        finally:
            await self._cleanup()
    
    async def _cleanup(self):
        """Cleanup resources"""
        if self._proactivity_task:
            self._proactivity_task.cancel()
        if self._status_task:
            self._status_task.cancel()
        if self._mic_meter_task:
            self._mic_meter_task.cancel()
        if self._system_monitor_task:
            self._system_monitor_task.cancel()
        if self._voice_debounce_task:
            self._voice_debounce_task.cancel()
        self.text_reader.stop_monitoring()
        self.sts_engine.stop()

    async def _status_loop(self):
        """Loga estado ATIVO/MUDO baseado no VAD."""
        while self.running:
            try:
                state = "ATIVO" if self._voice_active else "MUDO"
                if state != self._status_last:
                    self._log(f" {state}")
                    self._status_last = state
                await asyncio.sleep(self._status_interval)
            except Exception:
                await asyncio.sleep(self._status_interval)

    async def _system_monitor_loop(self):
        """Monitora CPU/RAM/Disco e avisa quando estiver alto."""
        while self.running:
            try:
                await asyncio.sleep(10)

                stats = self.system_monitor.get_stats()
                if self.ui and hasattr(self.ui, "set_system_stats"):
                    self.ui.set_system_stats(
                        stats.get("cpu", 0),
                        stats.get("ram", 0),
                        stats.get("disk", 0),
                        stats.get("gpu", None),
                        stats.get("proc_ram_mb", None),
                        stats.get("proc_ram_pct", None),
                    )

                if self.standby or self.snooze:
                    continue
                if (
                    self._event_loop
                    and not self._has_user_interacted
                    and self._event_loop.time() < self._startup_alert_until
                ):
                    continue
                if self._event_loop and self._event_loop.time() < self._monitor_alert_snooze_until:
                    continue
                if self._voice_active or self._ptt_is_down:
                    continue
                if self.sts_engine.is_speaking or self._processing_lock.locked():
                    continue

                if not self._monitor_proactive_alerts:
                    continue

                alerts = self.system_monitor.check_alerts(stats)
                if alerts:
                    msg = self.system_monitor.alert_message(stats, alerts)
                    if msg:
                        self._speak(msg)
                        if self.ui and hasattr(self.ui, "show_popup"):
                            self.ui.show_popup("Alerta Sistema", msg)
            except Exception:
                await asyncio.sleep(1)

    async def _mic_meter_loop(self):
        """Atualiza a linha reativa ao microfone na UI."""
        while self.running:
            try:
                if self.ui and hasattr(self.ui, "set_mic_level"):
                    energy = getattr(self.sts_engine, "last_energy", 0.0) or 0.0
                    threshold = self.sts_engine.get_vad_threshold()
                    level = energy / max(1.0, threshold * 2.5)
                    self.ui.set_mic_level(level)
                await asyncio.sleep(0.05)
            except Exception:
                await asyncio.sleep(0.1)
    
    async def _proactivity_loop(self):
        """Loop para verificar inatividade e acionar a proatividade da Crono"""
        import random
        while self.running:
            await asyncio.sleep(self.proactivity_check_interval)
            
            # Em stand-by/soneca, nÃ£o verifica inatividade nem loga
            if self.standby or self.snooze:
                continue

            # No interromper se j estiver falando ou processando
            if self.sts_engine.is_speaking or self._processing_lock.locked():
                continue
            if self._voice_active or self._ptt_is_down:
                continue
            if not self.proactive_vision_enabled:
                continue
            
            idle_duration = asyncio.get_event_loop().time() - self.last_interaction_time
            threshold = random.randint(self.min_idle_time, self.max_idle_time)
            
            self._log(f" Verificando inatividade: {idle_duration:.1f}s (threshold: {threshold}s)")
            
            if idle_duration > threshold:
                self._log(f" Inatividade detectada! Acionando proatividade...")
                await self._handle_proactivity(idle_duration)
    
    async def _handle_proactivity(self, idle_duration: float):
        """Lida com a proatividade quando detectada inatividade"""
        if self.standby:
            self._log("Stand-by ativo: proatividade ignorada.")
            self.last_interaction_time = asyncio.get_event_loop().time()
            return
        if self.snooze:
            self._log("Soneca ativa: proatividade ignorada.")
            self.last_interaction_time = asyncio.get_event_loop().time()
            return
        if not self.proactive_vision_enabled:
            self._log("Visao proativa desativada: pulando analise de tela.")
            self.last_interaction_time = asyncio.get_event_loop().time()
            return
        # Protocolo de primeiro uso: perguntar nome em momentos aleatÃ³rios
        if self._should_prompt_name():
            import time
            self._awaiting_user_name = True
            self._last_name_prompt_time = time.time()
            question = "Oi! Qual seu nome"
            self._speak(question)
            self.temp_memory.set_last_ai_response(question)
            self.last_interaction_time = asyncio.get_event_loop().time()
            return

        screen_data = None
        screen_captured = False
        
        try:
            # Tirar screenshot e analisar
            self._log("Capturando tela para anÃ¡lise proativa...")
            desc = await asyncio.to_thread(
                capture_and_analyze_screen,
                player=self.ui,
                session_memory=self.temp_memory,
                user_question="Descreva brevemente o que estÃ¡ na tela",
                speak=False,
                stream=True
            )
            screen_data = {"activity": "unknown", "description": desc}
            screen_captured = True
            if desc:
                self._log(f"Tela capturada: {desc[:100]}...")
        except Exception as e:
            self._log(f" Erro ao capturar tela: {e}")
            # Mesmo com erro, continuamos para tentar fazer um comentÃ¡rio
            screen_data = None
        
        # Obter comentÃ¡rio proativo com base no contexto visual
        comment = None
        if screen_data and screen_data.get("description"):
            prompt = (
                "CONTEXTO_VISUAL:\n"
                f"{screen_data.get('description')}\n\n"
                "INSTRUCAO: Gere um comentÃ¡rio curto e natural baseado no contexto visual. "
                "NÃ£o descreva a tela inteira. NÃ£o diga 'a tela mostra'. "
                "Seja pessoal e leve (ex: percebi que vocÃª gosta de X)."
            )
            try:
                llm_output = await asyncio.to_thread(
                    get_llm_output,
                    user_text=prompt,
                    memory_block=self._build_memory_block(),
                    include_reasoning=False,
                    reasoning_format="hidden",
                    reasoning_effort="low",
                    allow_reasoning_hint=False,
                    structured_outputs=False,
                    use_tools=False,
                    tool_choice=None,
                )
                comment = llm_output.get("response")
            except Exception as e:
                self._log(f" Falha ao gerar comentÃ¡rio proativo: {e}")

        if not comment:
            # Fallback
            self._log(f"Solicitando comentÃ¡rio proativo (idle: {idle_duration:.1f}s)...")
            comment = await self.emotion_commentator.check_and_comment(idle_duration, screen_data)
        
        if comment:
            self._log(f"ComentÃ¡rio proativo: {comment}")
            self._speak(comment, blocking=True)
            self.last_interaction_time = asyncio.get_event_loop().time()
        else:
            # Se nÃ£o fez comentÃ¡rio, apenas reiniciar relÃ³gio
            self._log("Nenhum comentÃ¡rio proativo gerado")
            self.last_interaction_time = asyncio.get_event_loop().time()
    
    async def _process_user_input(self, text: str):
        """Processar entrada do usuÃ¡rio atravÃ©s do pipeline organizado"""
        async with self._processing_lock:
            try:
                raw_text = text
                # Em stand-by/soneca, so acorda quando ouvir "crono/cronos".
                if self.standby or self.snooze:
                    if not self._is_sleep_wake(raw_text):
                        return
                    self.set_standby(False, speak=False)
                    self.set_snooze(False, speak=False)
                    wake_msg = await self._build_wake_reply(raw_text)
                    self._speak(wake_msg)
                    self.temp_memory.set_last_ai_response(wake_msg)
                    return
                # ConfirmaÃ§Ãµes pendentes tÃªm prioridade
                if await self._handle_confirmation_response(text):
                    return

                # Guardar contra eco do prÃ³prio TTS
                if self._is_probable_echo(raw_text):
                    self._log(f"Eco ignorado: '{raw_text}'")
                    return

                if self._is_short_noise(raw_text):
                    self._log(f"Entrada curta ignorada: '{raw_text}'")
                    return

                self._has_user_interacted = True

                # Protocolo de primeiro uso: capturar nome do usuÃ¡rio
                if self._awaiting_user_name:
                    self.last_interaction_time = asyncio.get_event_loop().time()
                    self.temp_memory.set_last_user_text(raw_text)
                    lowered = raw_text.strip().lower()
                    if any(x in lowered for x in ["nao", "nÃ£o"]) and any(x in lowered for x in ["quero", "prefiro", "agora n"]):
                        self._awaiting_user_name = False
                        self._speak("Tudo bem. Se quiser, me diga seu nome depois.")
                        self.temp_memory.set_last_ai_response("Tudo bem. Se quiser, me diga seu nome depois.")
                        return
                    name = self._extract_user_name(raw_text)
                    if not name or len(name) < 2 or name.lower() in {"sim", "nao", "nÃ£o"}:
                        self._speak("NÃ£o entendi seu nome. Pode repetir")
                        self.temp_memory.set_last_ai_response("NÃ£o entendi seu nome. Pode repetir")
                        return
                    self.memory.set_profile_field("user_name", name)
                    self._awaiting_user_name = False
                    reply = f"Prazer, {name}."
                    self._speak(reply)
                    self.temp_memory.set_last_ai_response(reply)
                    return

                # Se o usuÃ¡rio declarar o nome espontaneamente, salvar e nÃ£o perguntar mais
                if not self._user_name_known():
                    declared = self._detect_name_declaration(raw_text)
                    if declared and len(declared) >= 2:
                        self.memory.set_profile_field("user_name", declared)
                        self._awaiting_user_name = False
                        reply = f"Prazer, {declared}."
                        self._speak(reply)
                        self.temp_memory.set_last_ai_response(reply)
                        return

                # Vocabulrio do usurio (somente fora do modo escrito)
                if not self.typing_mode:
                    handled, response = maybe_handle_vocab_command(raw_text)
                    if handled:
                        if response:
                            self._speak(response)
                        return

                    corrected_text = correct_text(raw_text)
                else:
                    corrected_text = raw_text

                corrected_text = self._normalize_game_terms(corrected_text)
                self._game_context = self._detect_game_context(corrected_text)

                if corrected_text != raw_text:
                    self._log(f" Correção aplicada: '{raw_text}' -> '{corrected_text}'")

                try:
                    self.memory.add_message(role="user", content=corrected_text)
                except Exception:
                    pass
                self._refresh_memory_stats()
                if self.autonomous_memory:
                    try:
                        self.autonomous_memory.processar_mensagem_rapida(corrected_text)
                    except Exception:
                        pass

                # Fase 1: AnÃ¡lise de comando
                command_result = self.command_processor.analyze(corrected_text)

                # Fase 2: Executar comando especial se necessÃ¡rio
                if not await self._handle_special_command(command_result, corrected_text):
                    return

                # Mem0-lite: extrair memÃ³rias do texto do usuÃ¡rio
                self._mem0_ingest_user_text(corrected_text)

                # Modo escrito: digitar exatamente o que foi falado
                if self.typing_mode:
                    await self._handle_typing_mode(raw_text)
                    return

                # Exibir dica de memoria quando pergunta pessoal
                self._maybe_show_personal_memory_hint(corrected_text)

                # Consulta rÃ¡pida: status do timer
                timer_reply = self._maybe_answer_timer_query(corrected_text)
                if timer_reply:
                    self._speak(timer_reply)
                    self.temp_memory.set_last_ai_response(timer_reply)
                    return

                # Atalho de intencao (voz): comandos simples sem LLM
                quick_intent = self._detect_quick_intent(corrected_text)
                if quick_intent == "describe_screen":
                    self._handle_describe_screen({}, None, corrected_text)
                    self.last_interaction_time = asyncio.get_event_loop().time()
                    return

                # Detectar intencao por keywords (sem JSON)
                try:
                    result = detect_intent_by_keywords(corrected_text)
                except Exception as e:
                    self._log(f" Erro ao detectar intencao por keywords: {e}")
                    result = None
                if not result or not isinstance(result, tuple) or len(result) != 2:
                    intent, params = None, {}
                else:
                    intent, params = result
                if self.use_keyword_intents and intent and intent != "chat":
                    handler = self.action_handlers.get(intent)
                    if handler:
                        self._log(f" Intent (keyword): {intent}")
                        handler(self._normalize_params(params), None, corrected_text)
                        return

                # Fase 3: Executar pipeline de processamento
                await self.task_orchestrator.execute_pipeline(corrected_text)
                self._game_context = False
            except Exception as e:
                self._log(f"Erro ao processar entrada: {e}")

    async def _handle_special_command(self, command_result: CommandResult, text: str) -> bool:
        if command_result.command_type == CommandType.SHUTDOWN:
            await self._shutdown()
            return False

        if command_result.command_type == CommandType.RESTART:
            await self._restart()
            return False

        if command_result.command_type == CommandType.INTERRUPT:
            self._interrupt_response(text)
            return False

        if command_result.command_type == CommandType.STANDBY_ON:
            self.set_standby(True)
            return False

        if command_result.command_type == CommandType.STANDBY_OFF:
            self.set_standby(False)
            return False

        if command_result.command_type == CommandType.SNOOZE_ON:
            self.set_snooze(True)
            return False

        if command_result.command_type == CommandType.SNOOZE_OFF:
            self.set_snooze(False)
            return False

        if command_result.command_type == CommandType.TYPING_MODE_ON:
            self.typing_mode = True
            self._log(" Modo escrito ativado")
            self._speak("Modo escrito ativado. Vou apenas digitar o que voce falar.")
            return False

        if command_result.command_type == CommandType.TYPING_MODE_OFF:
            self.typing_mode = False
            self._log(" Modo escrito desativado")
            self._speak("Modo escrito desativado. Voltando ao normal.")
            return False

        if command_result.command_type == CommandType.VOCAB_IMPORT:
            if not command_result.should_process:
                self._log("Nenhum texto copiado para vocabulario!")
                self._speak("Copie o texto com as variantes e peca para eu corrigir o vocabulario.")
                return False

            added, skipped = import_variants_block(command_result.selected_text or "")
            msg = f"Vocabulario atualizado. Adicionados: {added}. Ignorados: {skipped}."
            self._log(msg)
            self._speak(msg)
            return False

        if command_result.command_type == CommandType.READ_SELECTED:
            if not command_result.should_process:
                self._log("Nenhum texto copiado!")
                self._speak("Desculpe, nao hatexto copiado. Copie um texto primeiro.", blocking=True)
                return False

            # Ignorar caminhos copiados a menos que o usuario peca explicitamente
            selected_text = command_result.selected_text or ""
            if selected_text and self._looks_like_path(selected_text) and not self._mentions_selected_text(text):
                self._log("Texto copiado parece um caminho. Ignorando sem pedido explicito.")
                return True

            # Processar texto selecionado
            await self._process_selected_text(text, command_result.selected_text)
            return False

        return True


    def set_standby(self, enabled: bool, speak: bool = True):
        self.standby = bool(enabled)
        if self.standby:
            self.snooze = False
        self._apply_listening_mode()
        if self.ui and hasattr(self.ui, "set_standby_state"):
            self.ui.set_standby_state(self.standby)
        if self.ui and hasattr(self.ui, "set_snooze_state") and self.standby:
            self.ui.set_snooze_state(False)
        try:
            self.last_interaction_time = asyncio.get_event_loop().time()
        except Exception:
            pass

    def set_proactive_vision(self, enabled: bool, speak: bool = False):
        self.proactive_vision_enabled = bool(enabled)
        if self.ui and hasattr(self.ui, "set_proactive_vision_state"):
            self.ui.set_proactive_vision_state(self.proactive_vision_enabled)
        state = "ativada" if self.proactive_vision_enabled else "desativada"
        self._log(f" Visão proativa {state}")
        if speak:
            msg = "Visão proativa ativada." if self.proactive_vision_enabled else "Visão proativa desativada."
            self._speak(msg)

    def set_snooze(self, enabled: bool, speak: bool = True):
        self.snooze = bool(enabled)
        if self.snooze:
            self.standby = False
        if self.ui and hasattr(self.ui, "set_snooze_state"):
            self.ui.set_snooze_state(self.snooze)
        if self.ui and hasattr(self.ui, "set_standby_state") and self.snooze:
            self.ui.set_standby_state(False)
        self._apply_listening_mode()
        try:
            self.last_interaction_time = asyncio.get_event_loop().time()
        except Exception:
            pass
        if speak:
            if self.snooze:
                self._speak("Modo soneca ativado. Vou pausar respostas e a Visão, mas posso acordar com seu comando.")
            else:
                self._speak("Modo soneca desativado. Estou de volta.")

    def _apply_listening_mode(self):
        if self.standby:
            # Mantem escuta para detectar palavra de wake.
            self.sts_engine.set_listening(True)
            return
        if self.snooze:
            self.sts_engine.set_listening(True)
            return
        if self._ptt_enabled:
            self.sts_engine.set_listening(self._ptt_is_down)
        else:
            self.sts_engine.set_listening(True)

    def set_ptt_enabled(self, enabled: bool, speak: bool = False):
        enabled = bool(enabled)
        if enabled and not kb:
            self._ptt_enabled = False
            self._ptt_is_down = False
            if self.ui and hasattr(self.ui, "set_ptt_state"):
                self.ui.set_ptt_state(False)
            self._speak("Nao consigo ativar PTT sem o modulo keyboard.")
            return

        self._ptt_enabled = enabled
        if not self._ptt_enabled:
            self._ptt_is_down = False
        self._apply_listening_mode()
        if self.ui and hasattr(self.ui, "set_ptt_state"):
            self.ui.set_ptt_state(self._ptt_enabled)
        self._log(f"PTT {'ativado' if self._ptt_enabled else 'desativado'}")
        if speak:
            self._speak("PTT ativado." if self._ptt_enabled else "PTT desativado.")

    def _unregister_ptt_hooks(self):
        if not kb:
            return
        try:
            if self._ptt_press_hook is not None:
                kb.unhook(self._ptt_press_hook)
        except Exception:
            pass
        try:
            if self._ptt_release_hook is not None:
                kb.unhook(self._ptt_release_hook)
        except Exception:
            pass
        self._ptt_press_hook = None
        self._ptt_release_hook = None

    def _register_ptt_hooks(self):
        if not kb:
            self._ptt_enabled = False
            return False
        self._unregister_ptt_hooks()
        try:
            self._ptt_press_hook = kb.on_press_key(self._ptt_key, self._on_ptt_down)
            self._ptt_release_hook = kb.on_release_key(self._ptt_key, self._on_ptt_up)
            return True
        except Exception as e:
            self._log(f" Falha ao registrar PTT ({self._ptt_key}): {e}")
            self._ptt_enabled = False
            self._ptt_is_down = False
            return False

    def set_ptt_key(self, key: str, speak: bool = False):
        clean = str(key or "").strip().lower()
        if not clean:
            clean = "insert"
        self._ptt_key = clean

        if kb:
            ok = self._register_ptt_hooks()
            if not ok and self.ui and hasattr(self.ui, "set_ptt_state"):
                self.ui.set_ptt_state(False)
        else:
            self._ptt_enabled = False
            self._ptt_is_down = False

        if self.ui and hasattr(self.ui, "set_ptt_key"):
            self.ui.set_ptt_key(self._ptt_key)
        self._apply_listening_mode()
        self._log(f"Tecla PTT definida para: {self._ptt_key}")
        if speak:
            self._speak(f"Tecla de PTT atualizada para {self._ptt_key}.")

    async def _handle_typing_mode(self, text: str):
        if not text or not text.strip():
            return
        self.last_interaction_time = asyncio.get_event_loop().time()
        self.temp_memory.set_last_user_text(text)
        await asyncio.to_thread(
            type_text_action,
            {"text": text, "click_before": False},
            None,
            self.ui,
            self.temp_memory
        )
    
    async def _process_selected_text(self, command: str, selected_text: str):
        """Processa texto selecionado com o comando do usurio"""
        # Combinar o comando com o texto copiado
        full_request = (
            f"{command}\n\nTexto copiado:\n{selected_text}\n\n"
            "INSTRUCAO: Responda apenas com texto. Nao abra sites."
        )
        
        self._log(f" Processando texto copiado...")
        self.temp_memory.set_last_user_text(full_request)
        
        # Build context
        memory_block = self._build_memory_block()
        
        # Get LLM response
        llm_output = await asyncio.to_thread(
            get_llm_output,
            user_text=full_request,
            memory_block=memory_block,
            include_reasoning=self.include_reasoning,
            reasoning_format=self.reasoning_format,
            reasoning_effort=self.reasoning_effort,
            use_prompt_cache=self.use_prompt_cache,
            structured_outputs=self.structured_outputs,
            use_tools=self.use_tools,
            tool_choice=self.tool_choice
        )
        
        # Process output
        await self._process_llm_output(llm_output, full_request)
        self.text_reader.clear_last_selected()
    
    async def _shutdown(self):
        """Graceful shutdown"""
        self._speak("Desligando o sistema. até logo, senhor.", blocking=True)
        
        try:
            self.memory.prune_summaries(max_summaries=200)
            self.memory.prune_old_messages(
                max_messages_per_conversation=5000,
                keep_days=90
            )
            self.memory.vacuum()
        except Exception:
            pass
        
        self.running = False
        os._exit(0)


    def _load_automations(self) -> str:
        """Load custom automations and skills from the automations folder"""
        auto_dir = os.path.join(BASE_DIR, "automations")
        if not os.path.exists(auto_dir):
            return ""

        automations = []
        for file in os.listdir(auto_dir):
            if file.endswith((".txt", ".md", ".json")):
                path = os.path.join(auto_dir, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            automations.append(f"[{file}]: {content}")
                except Exception:
                    continue

        return "\n".join(automations) if automations else ""

    def _build_memory_block(self) -> dict:
        """Build context block for LLM"""
        import datetime
        memory_block = {
            "current_time": datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        }
        # Short-term memory (last 20 messages)
        recent_msgs = self.memory.get_recent_messages(limit=20)
        if recent_msgs:
            formatted = []
            for m in recent_msgs:
                role = m.get("role", "unknown")
                text = m.get("content", "")
                formatted.append(f"{role}: {text}")
            memory_block["short_term_messages"] = "\n".join(formatted)
        # Ãšltimo turno explÃ­cito (ajuda a resolver referÃªncias)
        last_user = self.temp_memory.get_last_user_text() or ""
        last_ai = self.temp_memory.get_last_ai_response() or ""
        if last_user or last_ai:
            memory_block["recent_turn"] = f"user: {last_user}\nassistant: {last_ai}".strip()

        # Long-term memory (thought mode always active)
        query = self._clean_memory_query(last_user)
        if query:
            hits = self.memory.search_long_term(query, limit=5)
            if hits:
                formatted_hits = []
                for h in hits:
                    when = self._fmt_ts(h.get("ts"))
                    formatted_hits.append(f"[{when}] {h.get('content')}")
                memory_block["long_term_hits"] = "\n".join(formatted_hits)

        # Visual context (in-memory)
        visual = self.temp_memory.get_visual_context()
        if visual:
            memory_block["recent_screen_analysis"] = visual

        # Persisted visual memory
        try:
            last_screen = self.memory.get_last_screen()
            if last_screen:
                memory_block["last_screen_description"] = last_screen.get("description")
            last_image = self.memory.get_last_image()
            if last_image:
                memory_block["last_image_description"] = last_image.get("description")
            last_site = self.memory.get_last_opened_website()
            if last_site:
                memory_block["last_opened_website"] = last_site.get("url")
        except Exception:
            pass

        # Autonomous long-term memory
        try:
            if self.autonomous_memory:
                auto_mem = self.autonomous_memory.formatar_memorias()
                if auto_mem:
                    memory_block["autonomous_memory"] = auto_mem
        except Exception:
            pass

        # Pending intent
        if self.temp_memory.has_pending_intent():
            memory_block["_pending_intent"] = self.temp_memory.pending_intent
            memory_block["_collected_params"] = str(self.temp_memory.get_parameters())

        # Active project
        project = self.temp_memory.get_active_project()
        if project:
            memory_block["current_project"] = project["name"]
            memory_block["project_path"] = project["path"]
            memory_block["project_context"] = project["context"]

        # Custom Automations (System Skills)
        automations = self._load_automations()
        if automations:
            memory_block["custom_automations_skills"] = automations

        return {k: v for k, v in memory_block.items() if v}

    def _apply_memory_update(self, llm_output: dict | None):
        """Persist structured memory updates from the LLM."""
        if not isinstance(llm_output, dict):
            return
        memory_update = llm_output.get("memory_update")
        if isinstance(memory_update, dict) and memory_update:
            try:
                self.memory.update_profile_from_memory_update(memory_update)
            except Exception as e:
                self._log(f" Falha ao atualizar memoria: {e}")
    
    async def _process_llm_output(self, llm_output: dict, user_text: str):
        """Process LLM output and execute actions with streaming TTS"""
        try:
            plan = normalize_plan(llm_output)
            valid, error = validate_plan(plan)
            if not valid:
                self._log(f"Plano invalido: {error}")
                self._speak("Recebi um plano invalido. Pode reformular o pedido")
                return

            if plan.needs_clarification:
                question = plan.clarifying_question or "Preciso de mais detalhes."
                self._speak(question)
                return

            if plan.response and not plan.plan:
                self._speak(plan.response)
                if self.include_reasoning and llm_output.get("reasoning"):
                    self._speak(str(llm_output.get("reasoning")))
                return

            if not plan.plan:
                self._log("Plano vazio")
                self._speak("Nenhuma acao foi planejada.")
                return

            self.temp_memory.set_pending_plan(plan, step_index=0)
            await self._execute_plan_steps(plan, start_index=0)

        except Exception as e:
            self._log(f"Erro ao processar LLM output: {e}")
            print(f"LLM output processing error: {type(e).__name__}: {e}")
    async def _execute_plan_steps(self, plan, start_index: int = 0, skip_confirmation_step_id: str | None = None):
        """Execute plan steps sequentially with risk policy and confirmation."""
        for i in range(start_index, len(plan.plan)):
            if self.sts_engine.interrupt_requested:
                self.sts_engine.interrupt_requested = False
                return

            step = plan.plan[i]
            if step.intent == "system_command":
                last_text = (self.temp_memory.get_last_user_text() or "").strip()
                if not self._user_requested_system_command(last_text):
                    self._log("system_command bloqueado: pedido nao explicito de terminal/powershell.")
                    self._speak("Esse pedido nao requer comando de terminal. Vou responder sem executar comandos.")
                    continue
            step.risk = assess_risk(step)
            step.requires_confirmation = requires_confirmation(step.risk)
            self._log(f"RISK_AVALIADO: step_index={i} intent={step.intent} risk={step.risk}")

            if skip_confirmation_step_id and step.step_id == skip_confirmation_step_id:
                step.requires_confirmation = False
            # Lenient: nunca confirmar aes sensveis No destrutivas
            if step.risk != "destructive":
                step.requires_confirmation = False

            if step.requires_confirmation:
                self.temp_memory.set_pending_plan(plan, step_index=i)
                self.temp_memory.set_confirmation(step.step_id, step.summary)
                summary = step.summary or f"Executar {step.intent}"
                self._speak(f"Acao sensivel detectada: {summary}. Confirmar")
                return
            # Evitar abrir sites quando o pedido e sobre texto ou explicacao
            last_text = (self.temp_memory.get_last_user_text() or "")
            lowered = last_text.lower()
            if "texto copiado:" in lowered or any(k in lowered for k in [
                "resuma", "resumir", "resumo",
                "analise", "analisar", "analisa",
                "explique", "explicar", "explica",
                "traduz", "traduzir", "traduza"
            ]):
                if step.intent in {"open_website"}:
                    self._log(f"Bloqueado open_website em contexto de texto: {step.parameters}")
                    continue

            await self._execute_single_action(step, plan.goal, fallback_response=plan.response)

        self.temp_memory.clear_pending_plan()
    async def _execute_single_action(self, action, user_text: str, fallback_response: str | None = None):
        """Executa uma unica aÃ§Ã£o do LLM"""
        # Support PlanStep dataclass or dict
        intent = getattr(action, "intent", None) or (action.get("intent") if isinstance(action, dict) else "chat")
        raw_params = getattr(action, "parameters", None) or (action.get("parameters") if isinstance(action, dict) else {}) or {}
        params = self._normalize_params(raw_params)
        response = getattr(action, "response", None) if hasattr(action, "response") else (action.get("text") if isinstance(action, dict) else "")
        if intent == "chat" and (not response or not str(response).strip()):
            response = fallback_response or response
        summary = getattr(action, "summary", None) if hasattr(action, "summary") else (action.get("summary") if isinstance(action, dict) else None)
        step_id = getattr(action, "step_id", None) if hasattr(action, "step_id") else (action.get("step_id") if isinstance(action, dict) else None)

        self._log(f"Intent: {intent}")

        # Store AI response in memory
        if response and isinstance(response, str) and response.strip():
            self.temp_memory.set_last_ai_response(response)

        # Execute action handler
        handler = self.action_handlers.get(intent, self._handle_chat)
        success = True
        error_msg = None
        try:
            result = await asyncio.to_thread(handler, params, response, user_text)
            if isinstance(result, bool):
                success = result
        except Exception as handler_error:
            success = False
            error_msg = str(handler_error)
            self._log(f"Erro ao executar {intent}: {handler_error}")
            print(f"Handler error for {intent}: {type(handler_error).__name__}: {handler_error}")

        # Audit log
        try:
            self.temp_memory.record_action(intent, summary or intent, parameters=params, success=success)
        except Exception:
            pass

        if not success and error_msg:
            self._speak("Houve uma falha na execucao da acao.")
    def speak(self, text: str, blocking: bool = False):
        """Public wrapper for speaking; avoids using a private method."""
        return self._speak(text, blocking)

    def _speak(self, text: str, blocking: bool = False):
        """Speak with STS coordination"""
        if text:
            try:
                self._log(f"IA: {text}")
            except Exception:
                pass
            self._last_tts_text = text
            try:
                self.memory.add_message(role="assistant", content=text)
                self._refresh_memory_stats()
            except Exception:
                pass
            try:
                if self.autonomous_memory:
                    user_text = self.temp_memory.get_last_user_text() or ""
                    self.autonomous_memory.processar_interacao(user_text, text)
            except Exception:
                pass
            streaming_speak(text, self.ui, blocking=blocking)
    
    def _handle_open_app(self, params, response, user_text):
        # AO: No fala resposta, apenas executa
        open_app(params, None, self.ui, self.temp_memory)
    
    def _handle_close_app(self, params, response, user_text):
        # AO: No fala resposta, apenas executa
        close_app(params, None, self.ui, self.temp_memory)
    
    def _handle_type_text(self, params, response, user_text):
        type_text_action(params, response, self.ui, self.temp_memory)
    
    def _handle_press_key(self, params, response, user_text):
        press_key_action(params, response, self.ui, self.temp_memory)
    
    def _handle_open_website(self, params, response, user_text):
        # AO: No fala resposta, apenas executa
        open_website_action(params, None, self.ui, self.temp_memory)
        try:
            url = params.get("url") if isinstance(params, dict) else None
            if url:
                self.memory.set_last_opened_website(url)
        except Exception:
            pass
    
    def _handle_weather(self, params, response, user_text):
        import datetime
        text = (user_text or "").lower()
        # Se for pedido de data/hora, No chamar weather
        if any(k in text for k in ["dia de hoje", "data de hoje", "data atual", "que dia", "qual o dia"]):
            today = datetime.datetime.now().strftime("%d/%m/%Y")
            self._speak(f"Hoje  {today}.")
            return
        if any(k in text for k in ["hora", "horas", "que horas", "qual a hora"]) and not any(
            k in text for k in ["chuva", "chover", "vai chover", "clima", "tempo"]
        ):
            now_dt = datetime.datetime.now()
            hour = now_dt.hour
            minute = now_dt.strftime("%M")
            hour12 = hour % 12
            if hour12 == 0:
                hour12 = 12
            if 5 <= hour < 12:
                period = "da manhÃ£"
            elif 12 <= hour < 18:
                period = "da tarde"
            else:
                period = "da noite"
            msg = f"Agora sao {hour12}:{minute} {period}."
            self._speak(msg)
            if self.ui and hasattr(self.ui, "show_popup"):
                self.ui.show_popup("Horario", f"{hour12}:{minute} {period}")
            return

        city = (params or {}).get("city") if isinstance(params, dict) else None
        if not city:
            # Tenta extrair cidade do texto (ex: "em sao paulo")
            import re
            m = re.search(r"\bem\s+([a-zA-ZÃ€-Ã¿\s]+)", text)
            if m:
                city = m.group(1).strip(" .,!:;")
        if city:
            params = dict(params or {})
            params["city"] = city
            weather_action(params, self.ui, self.temp_memory)
        else:
            self._speak("Qual cidade vocÃª quer a previsÃ£o")
    
    def _handle_system_status(self, params, response, user_text):
        stats = self.system_monitor.get_stats()
        status = self.system_monitor.format_status(stats)
        alerts = []
        for key, threshold in self.system_monitor.thresholds.items():
            try:
                if key == "gpu" and stats.get("gpu") is None:
                    continue
                if float(stats.get(key, 0)) >= float(threshold):
                    alerts.append(key)
            except Exception:
                continue
        if alerts:
            msg = self.system_monitor.alert_message(stats, alerts) + " " + status
        else:
            msg = "Uso normal. " + status
        try:
            if self._event_loop:
                self._monitor_alert_snooze_until = self._event_loop.time() + max(0.0, self._monitor_alert_snooze_sec)
        except Exception:
            pass
        self._speak(msg)
        if self.ui and hasattr(self.ui, "show_popup"):
            self.ui.show_popup("Sistema", status)


    def _parse_timer_params(self, params: dict | None) -> tuple[str, str]:
        params = params or {}
        title = (params.get("title") or params.get("label") or params.get("name") or "temporizador").strip()
        duration_seconds = params.get("duration_seconds") or params.get("seconds") or params.get("sec")
        minutes = params.get("minutes") or params.get("mins") or params.get("min")
        hours = params.get("hours") or params.get("hour") or params.get("h")
        total = 0
        try:
            total += int(duration_seconds) if duration_seconds is not None else 0
        except Exception:
            pass
        try:
            total += int(minutes) * 60 if minutes is not None else 0
        except Exception:
            pass
        try:
            total += int(hours) * 3600 if hours is not None else 0
        except Exception:
            pass
        return title, self._human_duration_pt_br(total)

    def _human_duration_pt_br(self, total_seconds: int) -> str:
        total_seconds = max(0, int(total_seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        parts: list[str] = []
        if hours:
            parts.append(f"{hours} hora" + ("s" if hours != 1 else ""))
        if minutes:
            parts.append(f"{minutes} minuto" + ("s" if minutes != 1 else ""))
        if not parts and seconds:
            parts.append(f"{seconds} segundo" + ("s" if seconds != 1 else ""))
        return " e ".join(parts) if parts else "0 segundos"


    def _parse_timer_seconds(self, params: dict | None) -> int:
        params = params or {}
        duration_seconds = params.get("duration_seconds") or params.get("seconds") or params.get("sec")
        minutes = params.get("minutes") or params.get("mins") or params.get("min")
        hours = params.get("hours") or params.get("hour") or params.get("h")
        total = 0
        try:
            total += int(duration_seconds) if duration_seconds is not None else 0
        except Exception:
            pass
        try:
            total += int(minutes) * 60 if minutes is not None else 0
        except Exception:
            pass
        try:
            total += int(hours) * 3600 if hours is not None else 0
        except Exception:
            pass
        return int(total)

    def _handle_file_operation(self, params, response, user_text):
        file_operations(params, response, self.ui, self.temp_memory)
    
    def _handle_project(self, params, response, user_text):
        ok = project_manager(params, response, self.ui, self.temp_memory)
        try:
            action = (params or {}).get("action") if isinstance(params, dict) else None
            if ok and action == "start":
                active = self.temp_memory.get_active_project()
                if active:
                    name = active.get("name")
                    path = active.get("path")
                    ctx = active.get("context")
                    note = f"Projeto iniciado: {name} | {path} | {ctx}"
                    self.memory.add_long_term(note, kind="project", tags="projeto")
                    self._refresh_memory_stats()
        except Exception:
            pass
    
    def _handle_screen_control(self, params, response, user_text):
        screen_controller(params, self.ui, self.temp_memory)
    
    def _handle_describe_screen(self, params, response, user_text):
        if self.standby:
            self._speak("Modo stand-by ativo. Sem Visão agora.")
            return
        if self.snooze:
            self._speak("Modo soneca ativo. Sem Visão agora.")
            return
        # AO: Captura contexto visual e responde de forma natural ao pedido
        description = capture_and_analyze_screen(
            player=self.ui,
            session_memory=self.temp_memory,
            user_question=user_text,
            speak=False,
            stream=True,
            history=None
        )

        if not description:
            self._speak("Desculpe, No consegui analisar a tela agora.")
            return
        try:
            self.memory.set_last_screen(description, source="describe_screen")
            self.memory.set_last_image(description, source="describe_screen")
        except Exception:
            pass

        prompt = (
            "CONTEXTO_VISUAL:\n"
            f"{description}\n\n"
            "INSTRUCAO: Responda apenas ao que foi pedido. "
            "Nao diga 'a tela mostra' ou frases equivalentes. "
            "Nao descreva a tela inteira. Seja direto e natural.\n"
            f"PEDIDO: {user_text}"
        )

        llm_output = get_llm_output(
            prompt,
            memory_block=self._build_memory_block(),
            include_reasoning=False,
            reasoning_format="hidden",
            reasoning_effort="low",
            allow_reasoning_hint=False,
            use_prompt_cache=self.use_prompt_cache,
            structured_outputs=False,
            use_tools=False,
            tool_choice=None
        )
        try:
            response_text = llm_output.get("response")
        except Exception:
            response_text = None

        if response_text:
            self._speak(response_text)
        else:
            # Fallback: se o contexto jÃ¡ parecer uma resposta direta, use-o
            if self._looks_like_direct_visual_answer(description):
                self._speak(description.strip())
            else:
                self._speak("Ok. Analisei a tela e posso detalhar se quiser.")
    
    def _handle_youtube(self, params, response, user_text):
        if response:
            self._speak(response)

        if self.standby:
            self._speak("Modo stand-by ativo. Sem Visão agora.")
            return
        if self.snooze:
            self._speak("Modo soneca ativo. Sem Visão agora.")
            return
        
        capture_and_analyze_screen(
            player=self.ui,
            session_memory=self.temp_memory,
            user_question=user_text
        )
    
    def _handle_play_media(self, params, response, user_text):
        play_playlist_action(params, response, self.ui, self.temp_memory, user_text=user_text)
    
    def _handle_visual_navigate(self, params, response, user_text):
        if self.standby:
            self._speak("Modo stand-by ativo. Sem Visão agora.")
            return
        if self.snooze:
            self._speak("Modo soneca ativo. Sem Visão agora.")
            return
        ok, message = visual_navigator(params or {}, response, self.ui, self.temp_memory, user_text=user_text)
        if message:
            self._speak(message)
        if not ok:
            # fallback util: descreve contexto quando nao conseguiu clicar
            self._handle_describe_screen(params, response, user_text)

    def _handle_search_web(self, params, response, user_text):
        query = str((params or {}).get("query") or user_text or "").strip()
        if not query:
            self._speak("Qual consulta devo fazer na web")
            return
        if self._web_task and not self._web_task.done():
            self._speak("Ja existe uma busca web em andamento. Aguarde finalizar.")
            return
        ok, reason = self.ada_web_agent.check_ready()
        if not ok:
            self._log(f"A.D.A Web Agent indisponivel: {reason}")
            self._speak(
                "Integracao web indisponivel. Verifique conectividade e as chaves do LLM (Groq ou OpenRouter)."
            )
            return

        self._log(f"Iniciando A.D.A Web Agent para busca: {query}")
        self._speak("Buscando na web. Aguarde um momento.")

        async def _run_search():
            result = await self.ada_web_agent.search_web(query, user_request=user_text, timeout_sec=180)
            if result.success:
                answer = (result.text or "").strip()
                self._log(f"A.D.A Web Agent concluido em {result.elapsed_sec:.1f}s")
                try:
                    self.temp_memory.set_last_search(query, answer)
                except Exception:
                    pass
                if answer:
                    self._speak(answer)
                else:
                    self._speak("Conclui a busca, mas nao recebi um resumo textual.")
            else:
                self._log(f"Falha no A.D.A Web Agent: {result.error}")
                self._speak("Nao consegui concluir a busca web agora.")

        try:
            task = asyncio.get_running_loop().create_task(_run_search())
            self._web_task = task
        except RuntimeError:
            if self._event_loop:
                def _start():
                    task = self._event_loop.create_task(_run_search())
                    self._web_task = task
                self._event_loop.call_soon_threadsafe(_start)
            else:
                self._speak("Nao consegui iniciar a tarefa web neste momento.")

    def _handle_fetch_web_content(self, params, response, user_text):
        url = str((params or {}).get("url") or "").strip()
        if not url:
            self._speak("Qual URL devo buscar")
            return
        if self._web_task and not self._web_task.done():
            self._speak("Ja existe uma tarefa web em andamento. Aguarde finalizar.")
            return
        question = str((params or {}).get("question") or "").strip() or None

        ok, reason = self.ada_web_agent.check_ready()
        if not ok:
            self._log(f"A.D.A Web Agent indisponivel: {reason}")
            self._speak(
                "Integracao web indisponivel. Verifique conectividade e as chaves do LLM (Groq ou OpenRouter)."
            )
            return

        self._log(f"Iniciando A.D.A Web Agent para URL: {url}")
        self._speak("Analisando o conteudo da pagina. Aguarde.")

        async def _run_fetch():
            result = await self.ada_web_agent.fetch_web_content(url=url, question=question, timeout_sec=180)
            if result.success:
                answer = (result.text or "").strip()
                self._log(f"Conteudo web analisado em {result.elapsed_sec:.1f}s")
                if answer:
                    self._speak(answer)
                else:
                    self._speak("Conclui a analise da pagina, mas sem resumo textual.")
            else:
                self._log(f"Falha ao analisar URL: {result.error}")
                self._speak("Nao consegui analisar essa URL agora.")

        try:
            task = asyncio.get_running_loop().create_task(_run_fetch())
            self._web_task = task
        except RuntimeError:
            if self._event_loop:
                def _start():
                    task = self._event_loop.create_task(_run_fetch())
                    self._web_task = task
                self._event_loop.call_soon_threadsafe(_start)
            else:
                self._speak("Nao consegui iniciar a tarefa web neste momento.")

    def _handle_memory_durable_fact(self, params, response, user_text):
        fact = (params or {}).get("fact") or user_text
        fact = str(fact or "").strip()
        if not fact:
            self._speak("O que devo lembrar")
            return
        try:
            if "gosto de" in fact.lower():
                pref = fact.lower().split("gosto de", 1)[1].strip()
                if pref:
                    self.memory.add_preference(pref)
            project, person = self._extract_memory_scope(fact)
            if hasattr(self.memory, "add_scoped_note"):
                self.memory.add_scoped_note(fact, source="voice", project=project, person=person)
            else:
                self.memory.add_remember_note(fact, source="voice")
            self._speak("Ok. Vou lembrar disso.")
            self._refresh_memory_stats()
        except Exception:
            self._speak("Nao consegui salvar isso agora.")

    def _handle_search_personal_data(self, params, response, user_text):
        query = (params or {}).get("query") or user_text
        query = str(query or "").strip()
        if not query:
            self._speak("O que voce quer que eu lembre")
            return
        project, person = self._extract_memory_scope(query)
        hits = []
        try:
            if hasattr(self.memory, "search_long_term_scoped"):
                notes = self.memory.search_long_term_scoped(query=query, limit=3, project=project, person=person)
            else:
                notes = self.memory.search_notes(query, limit=3)
            hits.extend([n.get("note") or n.get("content") for n in notes if (n.get("note") or n.get("content"))])
        except Exception:
            pass
        try:
            profile = self.memory.get_profile()
            for k, v in profile.items():
                if query.lower() in str(v).lower():
                    hits.append(f"{k}: {v}")
        except Exception:
            pass
        if not hits:
            self._speak("Nao encontrei nada salvo sobre isso.")
            return
        response_text = "Encontrei: " + "; ".join(hits[:3])
        self._speak(response_text)

    def _handle_graphic_art(self, params, response, user_text):
        self._speak("Geracao de imagem nao esta habilitada aqui.")

    def _handle_load_skills(self, params, response, user_text):
        self._speak("Carregamento de habilidades nao esta configurado.")

    def _handle_multi_tool_parallel(self, params, response, user_text):
        tool_uses = (params or {}).get("tool_uses") or []
        if not tool_uses:
            self._speak("Nenhuma ferramenta para executar.")
            return
        for item in tool_uses:
            name = item.get("recipient_name") or ""
            arguments = self._normalize_params(item.get("parameters") or {})
            handler = self.action_handlers.get(name)
            if handler:
                handler(arguments, response, user_text)
    def _normalize_params(self, params):
        """Ensure handler parameters are always a dict."""
        return params if isinstance(params, dict) else {}
    def _handle_remember_note(self, params, response, user_text):
        note = (params or {}).get("note") or user_text
        note = str(note or "").strip()
        if not note:
            self._speak("O que exatamente devo lembrar")
            return
        try:
            project, person = self._extract_memory_scope(note)
            if hasattr(self.memory, "add_scoped_note"):
                self.memory.add_scoped_note(note, source="voice", project=project, person=person)
            else:
                self.memory.add_remember_note(note, source="voice")
            self._speak("Anotado.")
            self._refresh_memory_stats()
        except Exception:
            self._speak("NÃ£o consegui salvar isso agora.")
    def _extract_memory_scope(self, text: str) -> tuple[str | None, str | None]:
        import re
        t = str(text or "").strip()
        if not t:
            return None, None
        lower = t.lower()
        project = None
        person = None

        m = re.search(r"\bprojeto\s+([a-zA-Z0-9_\-\s]{2,})", lower)
        if m:
            project = m.group(1).strip(" .,;:!?")

        m2 = re.search(r"\b(pessoa|cliente|usuario|usu?rio)\s+([a-zA-Z0-9_\-\s]{2,})", lower)
        if m2:
            person = m2.group(2).strip(" .,;:!?")

        return project, person

    def _handle_clear_popups(self, params, response, user_text):
        if self.ui and hasattr(self.ui, "clear_popups"):
            self.ui.clear_popups()
        if response and response.strip():
            self._speak(response)
        else:
            self._speak("Popups limpos.")
    def _handle_knowledge_submit(self, text: str):
        text = str(text or "").strip()
        if not text:
            return
        try:
            self.memory.add_remember_note(text, source="ui")
            if self.ui:
                self.ui.show_popup("Conhecimento", "Salvo.")
            self._speak("Conhecimento salvo.")
            self._refresh_memory_stats()
        except Exception:
            if self.ui:
                self.ui.show_popup("Conhecimento", "Falha ao salvar.")
            self._speak("Nao consegui salvar isso agora.")

    def _handle_message_submit(self, text: str):
        text = str(text or "").strip()
        if not text:
            return
        if self._event_loop:
            asyncio.run_coroutine_threadsafe(self._process_user_input(text), self._event_loop)
            if self.ui:
                self.ui.show_popup("Mensagem", "Enviada.")
        else:
            if self.ui:
                self.ui.show_popup("Mensagem", "Sistema iniciando.")

    def _refresh_memory_stats(self):
        if not self.ui or not hasattr(self.ui, "update_memory_stats"):
            return
        try:
            stats = self.memory.get_stats()
            self.ui.update_memory_stats(stats)
        except Exception:
            pass

    def _clear_short_memory(self):
        try:
            self.memory.clear_short_term()
            if self.ui:
                self.ui.show_popup("Memoria", "Memoria de curto prazo limpa.")
        except Exception:
            if self.ui:
                self.ui.show_popup("Memoria", "Falha ao limpar curto prazo.")

    def _clear_long_memory(self):
        try:
            self.memory.clear_long_term()
            if self.ui:
                self.ui.show_popup("Memoria", "Memoria de longo prazo limpa.")
        except Exception:
            if self.ui:
                self.ui.show_popup("Memoria", "Falha ao limpar longo prazo.")

    def _clear_visual_memory(self):
        try:
            self.memory.clear_visual()
            if self.ui:
                self.ui.show_popup("Memoria", "Memoria visual limpa.")
        except Exception:
            if self.ui:
                self.ui.show_popup("Memoria", "Falha ao limpar memoria visual.")
    def _handle_chat(self, params, response, user_text):
        if response and response.strip():
            self._speak(response)
            self._mem0_add_summary(user_text, response)
        else:
            self._speak("Pode repetir de outra forma")
    
    def _handle_create_directory(self, params, response, user_text):
        """Handler para criar diretÃ³rio"""
        path = params.get('path', '')
        name = params.get('name', '')
        use_subprocess = params.get('use_subprocess', True)
        
        if not path:
            self._log("Caminho nÃ£o especificado")
            self._speak("Por favor, especifique o caminho onde deseja criar o diretÃ³rio.")
            return
        
        result = self.file_manager.create_directory(path, name, use_subprocess)
        
        if result['success']:
            self._log(f"DiretÃ³rio criado: {result['path']}")
            self._speak(f"DiretÃ³rio criado com sucesso em {result['path']}")
        else:
            self._log(f"Erro ao criar diretÃ³rio: {result['error']}")
            self._speak(f"Desculpe, nÃ£o foi possÃ­vel criar o diretÃ³rio. {result['error']}")
    
    def _handle_scan_directory(self, params, response, user_text):
        """Handler para escanear diretÃ³rio"""
        path = params.get('path', '')
        recursive = params.get('recursive', False)
        include_hidden = params.get('include_hidden', False)
        
        if not path:
            self._log("Caminho nÃ£o especificado")
            self._speak("Por favor, especifique o caminho do diretÃ³rio que deseja escanear.")
            return
        
        result = self.file_manager.scan_directory(path, recursive, include_hidden)
        
        if result['success']:
            scan_data = result['result']
            self._log("Escaneamento concluÃ­do:")
            self._log(f"   Arquivos: {scan_data['total_files']}")
            self._log(f"   DiretÃ³rios: {scan_data['total_directories']}")
            self._log(f"   Tamanho total: {scan_data['total_size_human']}")
            
            message = f"Escaneamento concluÃ­do. Encontrei {scan_data['total_files']} arquivos e {scan_data['total_directories']} diretÃ³rios. Tamanho total: {scan_data['total_size_human']}."
            self._speak(message)
        else:
            self._log(f"Erro ao escanear diretÃ³rio: {result['error']}")
            self._speak(f"Desculpe, nÃ£o foi possÃ­vel escanear o diretÃ³rio. {result['error']}")
    
    def _handle_list_directory(self, params, response, user_text):
        """Handler para listar diretÃ³rio"""
        path = params.get('path', '')
        detailed = params.get('detailed', True)
        
        if not path:
            self._log("Caminho nÃ£o especificado")
            self._speak("Por favor, especifique o caminho do diretÃ³rio que deseja listar.")
            return
        
        result = self.file_manager.list_directory(path, detailed)
        
        if result['success']:
            items = result['items']
            self._log(f" Contedo de {path}:")
            self._log(f"   Total de itens: {result['count']}")
            
            # Listar primeiros 10 itens
            for i, item in enumerate(items[:10]):
                icon = "" if item['is_directory'] else ""
                size = item['size_human'] if detailed else ""
                self._log(f"   {icon} {item['name']} {size}")
            
            if len(items) > 10:
                self._log(f"   ... e mais {len(items) - 10} itens")
            
            message = f"Encontrei {result['count']} itens no diretrio. Os primeiros so: {', '.join([item['name'] for item in items[:5]])}."
            self._speak(message)
        else:
            self._log(f" Erro ao listar diretrio: {result['error']}")
            self._speak(f"Desculpe, No foi possvel listar o diretrio. {result['error']}")
    
    def _handle_get_file_info(self, params, response, user_text):
        """Handler para obter informaes de arquivo"""
        path = params.get('path', '')
        
        if not path:
            self._log(" Caminho No especificado")
            self._speak("Por favor, especifique o caminho do arquivo que deseja obter informaes.")
            return
        
        result = self.file_manager.get_file_info(path)
        
        if result['success']:
            metadata = result['metadata']
            self._log(f" Informaes do arquivo:")
            self._log(f"   Nome: {metadata['name']}")
            self._log(f"   Tipo: {metadata['type']}")
            self._log(f"   Tamanho: {metadata['size_human']}")
            self._log(f"   Criado: {metadata['created']}")
            self._log(f"   Modificado: {metadata['modified']}")
            
            message = f"O arquivo {metadata['name']} tem {metadata['size_human']} e  do tipo {metadata['type']}."
            self._speak(message)
        else:
            self._log(f" Erro ao obter informaes: {result['error']}")
            self._speak(f"Desculpe, No foi possvel obter informaes do arquivo. {result['error']}")

    def _handle_set_timer(self, params, response, user_text):
        """Handler para criar temporizador"""
        # Suporta timer por horÃ¡rio (time_of_day = "HH:MM")
        params = params or {}
        if isinstance(params, dict) and params.get("time_of_day"):
            try:
                tod = str(params.get("time_of_day"))
                import datetime
                now = datetime.datetime.now()
                hh, mm = tod.split(":", 1)
                target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                if target <= now:
                    target = target + datetime.timedelta(days=1)
                duration = int((target - now).total_seconds())
                params = dict(params)
                params.pop("time_of_day", None)
                params["duration_seconds"] = duration
                params.setdefault("title", f"timer {tod}")
            except Exception:
                pass
        set_timer_action(params, response, self.ui, self.temp_memory)
        try:
            title, human = self._parse_timer_params(params)
            duration = self._parse_timer_seconds(params)
            import time
            if duration > 0:
                self.temp_memory.set_last_timer(duration, title or None)
                now = time.time()
                self.temp_memory.set_last_timer_times(now, now + duration)
            if self.ui and hasattr(self.ui, "show_popup"):
                self.ui.show_popup("Temporizador", f"{title} - {human}")
                if self.ui and hasattr(self.ui, "add_timer"):
                    self.ui.add_timer(title, duration)
        except Exception:
            pass

    def _handle_schedule_calendar(self, params, response, user_text):
        """Handler para agendar no calendÃ¡rio (via arquivo .ics)"""
        schedule_calendar_action(params, response, self.ui, self.temp_memory)
        try:
            if self.ui and hasattr(self.ui, "show_popup"):
                title = (params or {}).get("title") or (params or {}).get("summary") or "Evento"
                when = (params or {}).get("start") or (params or {}).get("start_datetime") or (params or {}).get("datetime") or ""
                self.ui.show_popup("Agenda", f"{title} @ {when}".strip())
        except Exception:
            pass

    def _handle_cancel_timer(self, params, response, user_text):
        """Cancela o Ãºltimo temporizador ativo."""
        try:
            canceled = False
            if self.temp_memory:
                canceled = self.temp_memory.cancel_last_timer()
            if canceled:
                self._speak("Temporizador cancelado.")
            else:
                self._speak("NÃ£o encontrei um temporizador ativo para cancelar.")
        except Exception:
            self._speak("NÃ£o consegui cancelar o temporizador agora.")

    def _handle_system_command(self, params, response, user_text):
        """Handler para executar comando PowerShell"""
        if not self._user_requested_system_command(user_text):
            self._log(" Comando PowerShell ignorado: usuÃ¡rio nÃ£o pediu execuÃ§Ã£o explÃ­cita")
            self._speak("Esse pedido nÃ£o parece um comando do PowerShell. Se quiser, diga: 'execute no PowerShell: ...'.")
            return
        system_command_action(params, response, self.ui, self.temp_memory)

    def _user_requested_system_command(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        markers = [
            "powershell", "no powershell", "powershell:",
            "terminal", "no terminal", "cmd", "prompt",
            "execute o comando", "executa o comando",
            "rodar comando", "rode o comando",
            "comando:"
        ]
        return any(m in t for m in markers)


def main():
    """Entry point for STS-enabled Crono"""
    # Garantir UTF-8 no console (corrige caracteres como //)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

    from ui import CronoUI
    from llm import init_cerebro_runtime
    
    ui = CronoUI(size=(720, 520))
    ui.attach_stdout_stderr()
    
    # Configurar para operar no segundo monitor se disponvel
    def _on_monitor_toggle(enabled: bool):
        if enabled:
            ok = setup_secondary_monitor_mode(ui.root, width=720, height=520)
            ui.set_monitor_state(ok)
        else:
            move_window_to_primary(ui.root, width=720, height=520)
            move_cmd_to_primary()

    ui.set_monitor_toggle_callback(_on_monitor_toggle)

    moved = setup_secondary_monitor_mode(ui.root, width=720, height=520)
    ui.set_monitor_state(moved)
    ui.maximize()
    # Inicializar cerebro e prompt em ordem
    init_cerebro_runtime()

    orchestrator = CronoSTSOrchestrator(ui)
    
    def runner():
        asyncio.run(orchestrator.run())
    
    threading.Thread(target=runner, daemon=True).start()
    ui.start()


if __name__ == "__main__":
    main()











