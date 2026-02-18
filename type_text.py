import pyautogui
import time
from streaming_tts import streaming_speak

def type_text_action(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Digita texto na posio atual do cursor usando PyAutoGUI.
    """
    # Tenta obter texto dos parmetros, se no houver, usa o response do LLM
    text_to_type = (parameters or {}).get("text", "").strip()
    
    # Se no houver texto nos parmetros, usa o response do LLM
    if not text_to_type and response:
        text_to_type = response.strip()

    click_before = bool((parameters or {}).get("click_before", False))

    if not text_to_type:
        msg = "Senhor, no identifiquei o que devo digitar."
        if player:
            player.write_log(f"Crono: {msg}")
        streaming_speak(msg, player, blocking=True)
        return False

    # Feedback antes de digitar
    if player:
        player.write_log(f"Crono: Digitando texto...")

    try:
        # Pausa curta antes de comear
        time.sleep(0.5)
        
        # Opcional: clicar antes de digitar para focar o campo
        if click_before:
            pyautogui.click()
            time.sleep(0.1)

        # Digita o texto
        pyautogui.write(text_to_type, interval=0.01)
        
        # Pressiona Enter se solicitado
        if parameters.get("press_enter", False):
            time.sleep(0.2)
            pyautogui.press("enter")
        
        # Feedback aps digitar
        if player:
            player.write_log(f"Crono: Texto digitado com sucesso.")
            
        return True

    except Exception as e:
        msg = f"Senhor, no consegui digitar o texto."
        if player:
            player.write_log(f"{msg} ({e})")
        streaming_speak(msg, player, blocking=True)
        return False
