import time
import os
import pyautogui
from tts import edge_speak


def open_app(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Abre um aplicativo usando a busca do Windows.

    parmetros:
        - app_name (str)

    Comportamento de memria:
        - Usa APENAS memria de sesso
        - Sem gravaes em memria de longo prazo
    """

    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name and session_memory:
        app_name = session_memory.open_app or ""

    if not app_name:
        msg = "Senhor, no consegui determinar qual aplicativo abrir."
        if player:
            player.write_log(msg)
        edge_speak(msg, player)
        return False

    # Detect folder intent or existing folder name
    folder_name = app_name.lower().replace("pasta", "").strip()
    folder_path = None

    if os.path.isabs(app_name) and os.path.isdir(app_name):
        folder_path = app_name
    else:
        active_project = session_memory.get_active_project() if session_memory else None
        if active_project:
            candidate = os.path.join(active_project["path"], folder_name)
            if os.path.isdir(candidate):
                folder_path = candidate

        if not folder_path:
            user_home = os.path.expanduser("~")
            onedrive_root = os.environ.get("OneDrive") or os.path.join(user_home, "OneDrive")
            desktop_root = os.path.join(onedrive_root, "Desktop")
            if not os.path.exists(desktop_root):
                desktop_root = os.path.join(user_home, "Desktop")
            candidate = os.path.join(desktop_root, folder_name)
            if os.path.isdir(candidate):
                folder_path = candidate

    if folder_path:
        try:
            if response:
                edge_speak(response, player)
            os.startfile(folder_path)
            if session_memory:
                session_memory.set_open_app(folder_path)
            return True
        except Exception as e:
            msg = f"Senhor, falhei ao abrir a pasta {os.path.basename(folder_path)}."
            if player:
                player.write_log(f"{msg} ({e})")
            edge_speak(msg, player)
            return False

    if response:
        edge_speak(response, player)

    try:
        pyautogui.PAUSE = 0.1


        pyautogui.press("win")
        time.sleep(0.3)

        pyautogui.write(app_name, interval=0.03)
        time.sleep(0.2)

        pyautogui.press("enter")
        time.sleep(0.6)

        if session_memory:
            session_memory.set_open_app(app_name)

        return True

    except Exception as e:
        msg = f"Senhor, falhei ao abrir {app_name}."
        if player:
            player.write_log(f"{msg} ({e})")
        edge_speak(msg, player)
        return False
