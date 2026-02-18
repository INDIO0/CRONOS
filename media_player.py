import os
import re
import unicodedata
import webbrowser
from streaming_tts import streaming_speak

try:
    import pyperclip
except Exception:
    pyperclip = None

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLAYLIST_DIR = os.path.join(_PROJECT_ROOT, "PLAYLISTS")

_URL_RE = re.compile(r"(https://\S+|www\.\S+|youtu\.be/\S+)", re.IGNORECASE)


def _extract_link(text: str | None) -> str | None:
    if not text:
        return None
    match = _URL_RE.search(text.strip())
    if not match:
        return None
    link = match.group(0).rstrip('.,;:!)"]\'')
    if link.startswith("www."):
        link = "https://" + link
    if link.startswith("youtu.be/"):
        link = "https://" + link
    return link


def _get_clipboard_text() -> str | None:
    if not pyperclip:
        return None
    try:
        return pyperclip.paste()
    except Exception:
        return None


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _normalize_playlist_name(raw_name: str | None) -> str | None:
    if not raw_name:
        return None
    text = _strip_accents(raw_name.strip().lower())
    text = text.strip("\"' ")

    prefixes = [
        "abrir a", "abre a", "abrir", "abre",
        "tocar a", "toca a", "tocar", "toca",
        "play", "ouvir a", "ouvir",
        "criar a", "crie a", "criar", "crie",
        "salvar a", "salve a", "salvar", "salve",
        "nova", "novo"
    ]
    for prefix in prefixes:
        if text.startswith(prefix + " "):
            text = text[len(prefix):].strip()
            break

    for marker in ["playlist", "lista de reproducao"]:
        if marker in text:
            text = text.replace(marker, " ").strip()

    if text.endswith(".txt"):
        text = text[:-4].strip()

    text = " ".join(text.split())
    return text or None


def _sanitize_filename(name: str | None) -> str | None:
    if not name:
        return None
    invalid_chars = '<>:"/\\|*'
    cleaned = "".join(ch for ch in name if ch not in invalid_chars)
    cleaned = cleaned.strip()
    return cleaned or None


def _resolve_action(parameters: dict, user_text: str | None) -> str:
    action = (parameters.get("action") or parameters.get("mode") or parameters.get("operation") or "").strip().lower()
    if parameters.get("create") is True:
        return "create"
    if action in {"create", "criar", "novo", "nova", "save", "salvar"}:
        return "create"
    if user_text:
        text_lower = _strip_accents(user_text.lower())
        if any(k in text_lower for k in [
            "criar playlist", "crie a playlist", "crie playlist", "nova playlist",
            "salvar playlist", "salve a playlist", "salve playlist"
        ]):
            return "create"
    return "open"


def _find_playlist_file(target_name: str | None) -> str | None:
    if not target_name:
        return None
    if not os.path.exists(PLAYLIST_DIR):
        return None
    files = [f for f in os.listdir(PLAYLIST_DIR) if f.lower().endswith(".txt")]

    # Match priority: exact, startswith, contains
    for f in files:
        base = _strip_accents(os.path.splitext(f)[0].lower())
        if base == target_name:
            return os.path.join(PLAYLIST_DIR, f)
    for f in files:
        base = _strip_accents(os.path.splitext(f)[0].lower())
        if base.startswith(target_name):
            return os.path.join(PLAYLIST_DIR, f)
    for f in files:
        base = _strip_accents(os.path.splitext(f)[0].lower())
        if target_name in base:
            return os.path.join(PLAYLIST_DIR, f)
    return None


def play_playlist_action(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None,
    user_text: str | None = None,
) -> bool:
    """
    Toca uma playlist salva em arquivo de texto.
    Parametros:
        - name (str): Nome da playlist (ex: 'rock', 'treino')
        - query (str): Consulta de musica (compativel com LLM)
        - playlist_name (str): Nome da playlist (retornado pelo LLM)
        - action (str): "open" ou "create"
        - url/link/video_url (str): Link de video para salvar na playlist
    """
    action = _resolve_action(parameters, user_text)

    # Aceita 'name', 'query' ou 'playlist_name' para compatibilidade
    name_raw = parameters.get("name") or parameters.get("query") or parameters.get("playlist_name") or parameters.get("title")
    name = _normalize_playlist_name(name_raw) or _normalize_playlist_name(user_text)

    if not name:
        msg = "Qual o nome da playlist, senhor"
        if player:
            player.write_log(msg)
        streaming_speak(msg, player, blocking=True)
        return False

    target_name = _strip_accents(name.lower().strip())

    if action == "create":
        safe_name = _sanitize_filename(name)
        if safe_name and safe_name.lower().endswith(".txt"):
            safe_name = safe_name[:-4]
        if not safe_name:
            msg = "Nao consegui entender o nome da playlist. Pode repetir"
            if player:
                player.write_log(msg)
            streaming_speak(msg, player, blocking=True)
            return False

        if not os.path.exists(PLAYLIST_DIR):
            os.makedirs(PLAYLIST_DIR, exist_ok=True)

        link = _extract_link(parameters.get("url") or parameters.get("link") or parameters.get("video_url"))
        if not link:
            link = _extract_link(_get_clipboard_text())

        if not link:
            msg = "Nao encontrei nenhum link no seu copiar e colar. Copie o link do video e me peca para criar a playlist novamente."
            if player:
                player.write_log(msg)
            streaming_speak(msg, player, blocking=True)
            return False

        playlist_path = os.path.join(PLAYLIST_DIR, f"{safe_name}.txt")
        try:
            with open(playlist_path, "w", encoding="utf-8") as f:
                f.write(link + "\n")
            msg = f"Playlist '{safe_name}' criada com sucesso."
            if player:
                player.write_log(msg)
            streaming_speak(msg, player, blocking=True)
            return True
        except Exception as e:
            err = f"Erro ao criar a playlist: {e}"
            if player:
                player.write_log(err)
            streaming_speak("Houve um erro ao tentar criar o arquivo da playlist.", player, blocking=True)
            return False

    # 1. Busca direta ou parcial
    found_file = _find_playlist_file(target_name)

    # 2. Execucao
    if found_file:
        try:
            with open(found_file, "r", encoding="utf-8") as f:
                # Pega a primeira linha valida que parece um link
                lines = f.readlines()
                link = None
                for line in lines:
                    clean = line.strip()
                    link = _extract_link(clean)
                    if link:
                        break

            if link:
                # Feedback inicial se houver resposta do LLM (agora apos verificar que a playlist existe)
                if response:
                    streaming_speak(response, player, blocking=True)

                if player:
                    player.write_log(f"Crono: Abrindo playlist '{os.path.basename(found_file)}'")
                webbrowser.open(link)
                return True
            else:
                err = f"A playlist '{name}' existe, mas nao encontrei um link valido nela."
                if player:
                    player.write_log(err)
                streaming_speak(err, player, blocking=True)
                return False

        except Exception as e:
            print(f"Erro ao ler playlist: {e}")
            err = "Houve um erro ao tentar ler o arquivo da playlist."
            if player:
                player.write_log(err)
            streaming_speak(err, player, blocking=True)
            return False

    else:
        # Se nao achou, informa e lista as disponiveis
        available = []
        if os.path.exists(PLAYLIST_DIR):
            available = [f.replace(".txt", "") for f in os.listdir(PLAYLIST_DIR) if f.lower().endswith(".txt")]

        msg = f"Nao encontrei a playlist '{name}', senhor."
        if available:
            msg += f" As disponiveis sao: {', '.join(available)}."
        else:
            msg += " A pasta de playlists esta vazia."

        if player:
            player.write_log(msg)
        streaming_speak(msg, player, blocking=True)
        return False
