import webbrowser
from urllib.parse import quote_plus
from tts import edge_speak


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None
):
    """
    Ação de relatório meteorológico.
    Abre uma busca do Google pelo clima e fornece uma breve confirmação falada.
    """

    city = parameters.get("city")
    time_val = parameters.get("time")
    if not city or not isinstance(city, str):
        msg = "Senhor, a cidade está faltando para o relatório de clima."
        _speak_and_log(msg, player)
        return msg

    city = city.strip()

    if not time_val or not isinstance(time_val, str):
        time_msg = "hoje"
        time_query = "hoje"
    else:
        time_val = time_val.strip()
        time_msg = time_val
        time_query = time_val

    search_query = f"clima em {city} {time_query}"
    encoded_query = quote_plus(search_query)
    url = f"https://www.google.com/search?q={encoded_query}"

    try:
        webbrowser.open(url)
    except Exception:
        msg = f"Senhor, não consegui abrir o navegador para o relatório de clima."
        _speak_and_log(msg, player)
        return msg

    msg = f"Mostrando o clima para {city}, {time_msg}, senhor."
    _speak_and_log(msg, player)

    if session_memory:
        try:
            session_memory.set_last_search(
                query=search_query,
                response=msg
            )
        except Exception:
            pass  

    return msg


def _speak_and_log(message: str, player=None):
    """Auxiliar: TTS seguro"""
    try:
        edge_speak(message)
    except Exception:
        pass
