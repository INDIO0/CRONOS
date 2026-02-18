import base64
import json
import os
import re
from io import BytesIO

import pyautogui
from dotenv import load_dotenv
from groq import Groq


load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL") or "meta-llama/llama-4-maverick-17b-128e-instruct"
_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def _extract_target(parameters: dict, user_text: str) -> str:
    target = str((parameters or {}).get("target") or "").strip()
    if target:
        return target
    text = str(user_text or "").strip()
    if not text:
        return ""
    t = text.lower()
    for marker in ["clica no", "clique no", "clica em", "clique em", "aperta o", "aperte o", "pressiona o"]:
        if marker in t:
            idx = t.index(marker) + len(marker)
            return text[idx:].strip(" .,!?:;")
    return text


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def visual_navigator(parameters: dict, response: str | None = None, player=None, session_memory=None, user_text: str = "") -> tuple[bool, str]:
    """
    Navegacao visual por contexto de tela.
    Localiza um alvo textual na tela usando modelo de visao e clica no ponto encontrado.
    """
    if not _groq_client:
        return False, "Visao indisponivel: configure GROQ_API_KEY."

    target = _extract_target(parameters or {}, user_text or "")
    if not target:
        return False, "Nao identifiquei o alvo para navegar."

    try:
        screenshot = pyautogui.screenshot()
        width, height = screenshot.size
        screenshot.thumbnail((1280, 1280))
        buff = BytesIO()
        screenshot.save(buff, format="JPEG", quality=75)
        b64 = base64.b64encode(buff.getvalue()).decode("utf-8")

        prompt = (
            "Voce recebe uma imagem de tela e um alvo para clicar.\n"
            f"ALVO: {target}\n"
            f"RESOLUCAO_ORIGINAL: {width}x{height}\n"
            "Retorne APENAS JSON valido no formato:\n"
            '{"found": true|false, "x": int, "y": int, "confidence": 0-100, "reason": "texto curto"}\n'
            "Se nao encontrar alvo, use found=false e confidence baixo.\n"
            "x e y devem estar na resolucao original."
        )

        completion = _groq_client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=220,
        )
        payload = _parse_json((completion.choices[0].message.content or "").strip())
        found = bool(payload.get("found"))
        confidence = int(payload.get("confidence") or 0)
        x = int(payload.get("x") or -1)
        y = int(payload.get("y") or -1)
        reason = str(payload.get("reason") or "").strip()

        if not found or confidence < 55:
            return False, f"Nao encontrei com confianca suficiente. {reason}".strip()
        if x < 0 or y < 0 or x > width or y > height:
            return False, "Coordenadas invalidas retornadas pela visao."

        pyautogui.moveTo(x, y, duration=0.15)
        pyautogui.click(x, y)
        return True, f"Cliquei em {target}."
    except Exception as e:
        return False, f"Falha na navegacao visual: {type(e).__name__}: {e}"
