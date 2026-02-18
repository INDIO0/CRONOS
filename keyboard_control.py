import pyautogui
import time
from tts import edge_speak

def press_key_action(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Simula o pressionamento de uma tecla (ex: Enter, Space, Esc).
    """
    key = parameters.get("key", "enter").lower()
    
    # Mapeia nomes comuns em português para teclas do pyautogui
    key_mapping = {
        "enter": "enter",
        "espaço": "space",
        "esc": "esc",
        "tab": "tab",
        "voltar": "backspace",
        "apagar": "backspace"
    }
    
    target_key = key_mapping.get(key, key)

    try:
        if player:
            player.write_log(f"Crono: Pressionando a tecla {target_key}...")
        
        time.sleep(0.3) # Pausa curta
        pyautogui.press(target_key)
        
        if response:
            edge_speak(response, player)
            
        return True
    except Exception as e:
        print(f"Erro ao pressionar tecla: {e}")
        return False
