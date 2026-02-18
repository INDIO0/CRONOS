from tts import edge_speak


def screen_controller(parameters: dict, player=None, session_memory=None) -> bool:
    """
    Controle de tela desativado (sem APIs externas).
    """
    msg = "Controle de tela desativado no momento."
    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"Crono: {msg}")
        except Exception:
            pass
    edge_speak(msg, player)
    return False
