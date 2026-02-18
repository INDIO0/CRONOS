import os
import subprocess
import threading
import uuid
import time
from typing import Any

from tts import edge_speak


def _safe_log(player, text: str):
    if not text:
        return
    if player:
        try:
            player.write_log(text)
        except Exception:
            pass


def _ps_single_quote(text: str) -> str:
    """
    Escape a string for PowerShell single-quoted strings.
    In PowerShell, single quotes are escaped by doubling them.
    """
    return str(text or "").replace("'", "''")


def _human_duration_pt_br(total_seconds: int) -> str:
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

    if not parts:
        return "0 segundos"
    if len(parts) == 1:
        return parts[0]
    return " e ".join(parts[:2])


def _spawn_system_timer_popup(delay_seconds: int, message: str, caption: str = "Crono"):
    """
    Start a detached PowerShell process that waits and shows a MessageBox.
    This keeps working even if Crono closes.
    """
    delay_seconds = max(0, int(delay_seconds))
    msg_escaped = _ps_single_quote(message)
    cap_escaped = _ps_single_quote(caption)

    script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"Start-Sleep -Seconds {delay_seconds}; "
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.MessageBox]::Show('{msg_escaped}','{cap_escaped}') | Out-Null;"
    )

    creationflags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS

    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
            cwd=os.getcwd(),
        )
    except Exception:
        # Best-effort: timer still works via in-process TTS.
        pass


def set_timer_action(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None,
) -> bool:
    """
    Create a timer.

    Expected parameters:
      - duration_seconds (int) OR seconds/minutes/hours
      - title (str, optional)
      - system_notification (bool, optional): show a system popup when timer ends (default True)

    Behavior:
      - Starts an in-process timer that will speak when finished.
      - Optionally also schedules a system popup (works even if Crono closes).
    """
    params = parameters or {}

    title = (params.get("title") or params.get("label") or params.get("name") or "temporizador").strip()
    system_notification = params.get("system_notification")
    if system_notification is None:
        # Se há registro de timer em sessão, evita popup que não pode ser cancelado.
        if session_memory and hasattr(session_memory, "register_timer"):
            system_notification = False
        else:
            system_notification = True
    system_notification = bool(system_notification)

    duration_seconds: Any = (
        params.get("duration_seconds")
        or params.get("seconds")
        or params.get("sec")
    )
    minutes = params.get("minutes") or params.get("mins") or params.get("min")
    hours = params.get("hours") or params.get("hour") or params.get("h")

    # Normalize duration
    try:
        base = int(duration_seconds) if duration_seconds is not None else 0
    except Exception:
        base = 0
    try:
        base += int(minutes) * 60 if minutes is not None else 0
    except Exception:
        pass
    try:
        base += int(hours) * 3600 if hours is not None else 0
    except Exception:
        pass

    if base <= 0:
        msg = "Qual a duração do temporizadorExemplo: 5 minutos, 1 hora."
        _safe_log(player, f"Crono: {msg}")
        edge_speak(msg, player)
        return False

    human = _human_duration_pt_br(base)
    start_msg = response or f"Ok. Temporizador de {human} iniciado ({title})."
    _safe_log(player, f"Crono: {start_msg}")
    edge_speak(start_msg, player)

    end_msg = f"Tempo esgotado: {title}."
    cancel_event = threading.Event()
    timer_id = str(uuid.uuid4())

    if session_memory and hasattr(session_memory, "register_timer"):
        try:
            session_memory.register_timer(timer_id, title, base, cancel_event)
        except Exception:
            pass

    def _timer_worker():
        try:
            if cancel_event.wait(base):
                # Cancelado
                if session_memory and hasattr(session_memory, "complete_timer"):
                    try:
                        session_memory.complete_timer(timer_id, canceled=True)
                    except Exception:
                        pass
                return
        except Exception:
            return
        _safe_log(player, f"Crono: {end_msg}")
        edge_speak(end_msg, player)
        if session_memory and hasattr(session_memory, "complete_timer"):
            try:
                session_memory.complete_timer(timer_id, canceled=False)
            except Exception:
                pass

    threading.Thread(target=_timer_worker, daemon=True).start()

    if system_notification:
        _spawn_system_timer_popup(base, end_msg, caption="Crono - Temporizador")

    return True
