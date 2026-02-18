import os
import shutil
from tts import edge_speak

def file_operations(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Gerencia operaes de arquivos e pastas com conscincia do contexto do projeto.
    
    Parmetros:
        - action (str): 'create_folder', 'delete_folder', 'create_file', 'delete_file', 'read_file', 'edit_file', 'list_files'
        - path (str): Caminho (relativo ao projeto ou absoluto)
        - content (str, opcional): Contedo para escrever
    """
    action = parameters.get("action")
    path = parameters.get("path")
    content = parameters.get("content", "")

    # Intelligence: Resolve special folders
    assistant_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if path and "automations/" in path:
        # Resolve automations/skill.txt to the actual assistant folder
        filename = os.path.basename(path)
        path = os.path.join(assistant_root, "automations", filename)
    elif path and not os.path.isabs(path):
        active_project = session_memory.get_active_project() if session_memory else None
        if active_project:
            path = os.path.join(active_project["path"], path)
        else:
            user_home = os.path.expanduser("~")
            onedrive_root = os.environ.get("OneDrive") or os.path.join(user_home, "OneDrive")
            onedrive_desktop = os.path.join(onedrive_root, "Desktop")
            desktop_root = onedrive_desktop if os.path.exists(onedrive_desktop) else os.path.join(user_home, "Desktop")
            path = os.path.join(desktop_root, path)

    if not action or (not path and action != "list_files"):
        msg = "Senhor, ainda falta o caminho ou o nome do arquivo para concluir."
        if player:
            player.write_log(f"Crono: {msg}")
        edge_speak(msg, player)
        return False

    # For list_files without path, use project root
    if action == "list_files" and not path and active_project:
        path = active_project["path"]

    try:
        result_msg = ""
        
        if action == "create_folder":
            os.makedirs(path, exist_ok=True)
            result_msg = f"Pasta criada com sucesso, senhor."
            
        elif action == "delete_folder":
            if os.path.exists(path):
                shutil.rmtree(path)
                result_msg = f"Pasta {os.path.basename(path)} removida."
            else:
                result_msg = "A pasta no existe, senhor."
                
        elif action == "create_file":
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            result_msg = f"Arquivo {os.path.basename(path)} criado e salvo."
            
        elif action == "delete_file":
            if os.path.exists(path) and os.path.isfile(path):
                os.remove(path)
                result_msg = f"Arquivo {os.path.basename(path)} excludo."
            else:
                result_msg = "Arquivo no encontrado para excluso, senhor."
            
        elif action == "read_file":
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    file_data = f.read(800)
                result_msg = f"Lendo o arquivo: {file_data}"
                if len(file_data) >= 800: result_msg += "... (truncado)"
            else:
                result_msg = "Arquivo no encontrado, senhor."
                
        elif action == "edit_file":
            if os.path.exists(path):
                with open(path, "a", encoding="utf-8") as f:
                    f.write("\n" + content)
                result_msg = f"Informao adicionada ao arquivo {os.path.basename(path)}."
            else:
                result_msg = "Arquivo no encontrado para edio."

        elif action == "list_files":
            if os.path.exists(path):
                files = os.listdir(path)
                if not files:
                    result_msg = "O diretrio est vazio, senhor."
                else:
                    result_msg = f"Arquivos encontrados: {', '.join(files[:20])}"
            else:
                result_msg = "Diretrio no encontrado."

        if player:
            player.write_log(f"Crono: {result_msg}")
        
        edge_speak(response if response else result_msg, player)
        return True

    except Exception as e:
        err = f"Erro de arquivo: {e}"
        if player: player.write_log(f"Crono: {err}")
        edge_speak("Houve uma falha tcnica na operao de arquivo, senhor.", player)
        return False
