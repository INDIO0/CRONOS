import os
import subprocess
from tts import edge_speak

def close_app(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Fecha um aplicativo usando taskkill no Windows.
    """
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        msg = "Senhor, não consegui identificar qual aplicativo fechar."
        if player:
            player.write_log(f"Crono: {msg}")
        edge_speak(msg, player)
        return False

    if response:
        edge_speak(response, player)

    try:
        # We try to use taskkill. Many apps have the process name similar to the app name.
        # This is a basic implementation.
        process_name = app_name.lower()
        if not process_name.endswith(".exe"):
            process_name += ".exe"

        # Try to kill the process
        result = subprocess.run(["taskkill", "/F", "/IM", process_name], capture_output=True, text=True)
        
        if result.returncode == 0:
            success_msg = f"Fechei o {app_name}, senhor."
            if player:
                player.write_log(f"Crono: {success_msg}")
            # edge_speak(success_msg, player) # Already spoke the response if provided
            return True
        else:
            # If standard taskkill fails, maybe the process name is different.
            # We could implement a search, but for now let's report the failure.
            fail_msg = f"Senhor, não consegui encontrar o processo do {app_name} para fechar."
            if player:
                player.write_log(f"Crono: {fail_msg}")
            edge_speak(fail_msg, player)
            return False

    except Exception as e:
        msg = f"Senhor, falhei ao fechar {app_name}."
        if player:
            player.write_log(f"{msg} ({e})")
        edge_speak(msg, player)
        return False
