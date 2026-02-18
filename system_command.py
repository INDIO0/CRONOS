import os
import subprocess
from tts import edge_speak


def _safe_log(player, text: str):
    if not text:
        return
    if player:
        player.write_log(text)


def _trim_output(text: str, limit: int = 3000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncado)"


def _decode_subprocess_bytes(data: bytes) -> str:
    """
    Decode stdout/stderr from subprocess on Windows.

    Python often defaults to cp1252, but PowerShell commonly writes UTF-8 to pipes.
    This avoids the classic mojibake like "parâmetro" or "não".
    """
    if not data:
        return ""

    # Heuristic: UTF-16LE output usually has lots of NUL bytes.
    if data.count(b"\x00") > max(2, len(data) // 4):
        try:
            return data.decode("utf-16le", errors="replace")
        except Exception:
            pass

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Fallbacks for legacy console codepages.
    try:
        return data.decode("cp850", errors="replace")
    except Exception:
        return data.decode("cp1252", errors="replace")


def system_command_action(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Executa comandos PowerShell.

    Parmetros esperados:
      - command (str): comando PowerShell a executar
      - cwd (str, opcional): diretrio de trabalho
      - timeout_sec (int, opcional): timeout em segundos
    """
    command = (
        parameters.get("command")
        or parameters.get("cmd")
        or parameters.get("powershell")
        or parameters.get("ps")
    )
    cwd = parameters.get("cwd") or parameters.get("path")
    timeout_sec = parameters.get("timeout_sec") or parameters.get("timeout") or 20

    if not command or not str(command).strip():
        msg = "Qual comando voc quer que eu execute no PowerShell"
        _safe_log(player, f"Crono: {msg}")
        edge_speak(msg, player)
        return False

    command = str(command).strip()

    if cwd:
        cwd = os.path.expanduser(str(cwd))
        if not os.path.exists(cwd):
            msg = "O caminho informado no existe. Pode confirmar o diretrio"
            _safe_log(player, f"Crono: {msg}")
            edge_speak(msg, player)
            return False

    try:
        # Force UTF-8 output to avoid encoding issues in logs/tts.
        command_wrapped = (
            "& { "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "$OutputEncoding = [System.Text.Encoding]::UTF8; "
            f"{command}"
            " }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command_wrapped],
            capture_output=True,
            cwd=cwd,
            timeout=int(timeout_sec),
            shell=False,
        )
    except subprocess.TimeoutExpired:
        msg = "O comando demorou demais e foi interrompido."
        _safe_log(player, f"Crono: {msg}")
        edge_speak(msg, player)
        return False
    except Exception as e:
        msg = f"Falha ao executar o comando: {e}"
        _safe_log(player, f"Crono: {msg}")
        edge_speak("Houve um erro ao executar o comando.", player)
        return False

    stdout = _decode_subprocess_bytes(result.stdout).strip()
    stderr = _decode_subprocess_bytes(result.stderr).strip()
    combined = "\n".join([s for s in [stdout, stderr] if s])

    if combined:
        _safe_log(player, _trim_output(combined))

    if result.returncode == 0:
        if response:
            edge_speak(response, player)
            return True
        if stdout and len(stdout) <= 200:
            edge_speak(stdout, player)
        else:
            edge_speak("Comando executado. A sada foi registrada no log.", player)
        return True

    # Erro
    if stderr:
        short_err = stderr if len(stderr) <= 200 else stderr[:200] + "..."
        edge_speak(f"O comando falhou: {short_err}", player)
    else:
        edge_speak("O comando falhou.", player)
    return False
