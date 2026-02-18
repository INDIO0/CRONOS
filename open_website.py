import webbrowser
from tts import edge_speak

def open_website_action(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None
) -> bool:
    """
    Abre diretamente uma URL no navegador padrão.
    """
    url = parameters.get("url")
    
    if not url:
        msg = "Senhor, não identifiquei o endereço do site."
        if player: player.write_log(f"Crono: {msg}")
        edge_speak(msg, player)
        return False

    # Normalização básica
    if not url.startswith("http"):
        url = "https://" + url

    try:
        if player:
            player.write_log(f"Crono: Abrindo o site {url}...")
        
        webbrowser.open(url)
        
        if response:
            edge_speak(response, player)
            
        return True
    except Exception as e:
        print(f"Erro ao abrir site: {e}")
        return False
