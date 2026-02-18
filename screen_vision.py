import os
import base64
import pyautogui
from io import BytesIO
from dotenv import load_dotenv
from groq import Groq
from tts import edge_speak

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL") or "meta-llama/llama-4-maverick-17b-128e-instruct"

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def capture_and_analyze_screen(player=None, session_memory=None, user_question="", speak: bool = True, stream: bool = False, history: list | None = None):
    """
    Capture the screen, send to a vision model, and speak the description.
    Groq Vision (meta-llama/llama-4-maverick-17b-128e-instruct).
    """
    try:
        if player:
            player.write_log("Crono: Analisando sua tela...")

        screenshot = pyautogui.screenshot()
        screenshot.thumbnail((1024, 1024))
        buffered = BytesIO()
        screenshot.save(buffered, format="JPEG", quality=70)
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

        prompt = "Analise esta imagem e produza um contexto visual curto e objetivo."
        if user_question:
            prompt += f" Foque apenas no que e relevante para: {user_question}."
        prompt += " Evite descrever a tela inteira."
        prompt += " REGRAS CRITICAS: NAO repita a pergunta. NAO use hashtags (#). NAO use markdown. Seja direto."

        description = ""
        if groq_client:
            completion = groq_client.chat.completions.create(
                model=GROQ_VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        ],
                    }
                ],
                temperature=0.2,
                max_tokens=350,
            )
            description = completion.choices[0].message.content or ""
        else:
            print("[VISION] Groq client nao inicializado. Verifique GROQ_API_KEY.")
            description = ""

        description = description.replace("#", "").replace("*", "").strip()

        if session_memory and description:
            session_memory.add_visual_context(
                description=description,
                details=f"Pergunta do usuario: {user_question}" if user_question else ""
            )

        if speak and description:
            edge_speak(description)
        return description

    except Exception as e:
        error_msg = f"Erro ao analisar tela: {type(e).__name__}: {e}"
        print(f"{error_msg}")
        if player:
            player.write_log("Crono: Tive um erro ao tentar ver sua tela.")
        edge_speak("Desculpe, tive um erro ao tentar ver sua tela.")
        return None
