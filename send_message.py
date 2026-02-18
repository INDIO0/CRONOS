import time
import pyautogui
from tts import edge_speak

REQUIRED_PARAMS = ["receiver", "message_text"]

def send_message(parameters: dict, response: str | None = None, player=None, session_memory=None) -> bool:
    """
    Envia uma mensagem via aplicativo Windows (WhatsApp, Telegram, etc.)

    Suporte a mltiplas etapas: solicita parmetros ausentes usando a memria temporria.

    Parmetros esperados:
        - receiver (str): Destinatrio
        - message_text (str): Texto da mensagem
        - platform (str, padro: "WhatsApp"): Plataforma
    """

    if session_memory is None:
        msg = "Memria de sesso ausente, no  possvel prosseguir."
        if player:
            player.write_log(msg)
        edge_speak(msg, player)
        return False

    if parameters:
        session_memory.update_parameters(parameters)

    for param in REQUIRED_PARAMS:
        value = session_memory.get_parameter(param)
        if not value:
        
            session_memory.set_current_question(param)
            question_text = ""
            if param == "receiver":
                question_text = "Senhor, para quem devo enviar a mensagem"
            elif param == "message_text":
                question_text = "Senhor, o que devo dizer"
            elif param == "platform":
                question_text = "Senhor, qual plataforma devo usar(WhatsApp, Telegram, etc.)"
            else:
                question_text = f"Senhor, por favor, informe {param}."

            edge_speak(question_text, player)
            return False  

    receiver = session_memory.get_parameter("receiver").strip()
    platform = session_memory.get_parameter("platform").strip() or "WhatsApp"
    message_text = session_memory.get_parameter("message_text").strip()

    if response:
        edge_speak(response, player)

    try:
        pyautogui.PAUSE = 0.1

        pyautogui.press("win")
        time.sleep(0.3)
        pyautogui.write(platform, interval=0.03)
        pyautogui.press("enter")
        time.sleep(0.6)

        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.2)
        pyautogui.write(receiver, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.2)

        pyautogui.write(message_text, interval=0.03)
        pyautogui.press("enter")

        session_memory.clear_current_question()
        session_memory.clear_pending_intent()
        session_memory.update_parameters({})  

        # -----------------------------
        # Log de sucesso
        # -----------------------------
        success_msg = f"Senhor, mensagem enviada para {receiver} via {platform}."
        if player:
            player.write_log(success_msg)
        edge_speak(success_msg, player)

        return True

    except Exception as e:
        msg = f"Senhor, falhei ao enviar a mensagem. ({e})"
        if player:
            player.write_log(msg)
        edge_speak(msg, player)
        return False
