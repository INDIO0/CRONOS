# llm.py

import os
import json
import re
import uuid
import requests
from datetime import datetime
from dataclasses import asdict
from dotenv import load_dotenv
from groq import Groq
from core.plan_schema import normalize_plan

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, "core", "prompt.txt")
PROMPT_JSON_PATH = os.path.join(BASE_DIR, "core", "prompt.json")
CEREBRO_PATH = os.path.join(BASE_DIR, "core", "cerebro.json")

# Runtime globals (initialized later)
SYSTEM_PROMPT = None
LLM_INITIALIZED = False
LLM_CLIENT = None
LLM_CLIENT_GROQ = None
LLM_MODEL = None
LLM_GROQ_MODEL = None
LLM_OPENROUTER_MODEL = None
LLM_OPENROUTER_KEY = None
LLM_OPENROUTER_SITE_URL = None
LLM_OPENROUTER_APP_NAME = None
LLM_OPENROUTER_DISABLE_ON_402 = None
LLM_REASONING_EFFORT = None
LLM_INCLUDE_REASONING = False
LLM_REASONING_FORMAT = None
LLM_USE_PROMPT_CACHE = False
LLM_STRUCTURED_OUTPUTS = False
LLM_USE_TOOLS = False
LLM_TOOL_CHOICE = "auto"

_LLM_CACHE_ID = None
_LLM_CACHE_FINGERPRINT = None

def get_default_prompt() -> str:
    """Prompt padro embutido caso o arquivo no exista"""
    return """Voc  o Crono, um orquestrador determinstico. Sua nica funo  gerar planos estruturados em JSON ou respostas de chat.

PRINCPIOS OBRIGATRIOS:
- Retorne APENAS JSON vlido, sem markdown.
- NUNCA use tool calls, function calling, name/arguments ou qualquer formato de ferramenta. Retorne SOMENTE o JSON do envelope descrito acima.
- Nunca execute aes.
- Nunca controle o sistema.
- Se faltar informao, pea esclarecimento.

FORMATO DE SADA (JSON OBRIGATRIO):
{
  "plan_id": "uuid",
  "goal": "string",
  "needs_clarification": false,
  "clarifying_question": null,
  "plan": [
    {
      "step_id": "uuid",
      "intent": "open_app",
      "parameters": { "app_name": "excel" },
      "risk": "safe",
      "requires_confirmation": false,
      "summary": "Abrir o Excel"
    }
  ],
  "response": null
}

REGRAS RIGIDAS:
- Retorne somente JSON vlido.
- Nunca execute aes.
- Nunca comente fora do JSON.
- O risco real ser calculado pelo sistema. Use "risk": "safe" e "requires_confirmation": false por padro.
- Se for conversa, coloque o texto em "response" e deixe "plan" como lista vazia.
- Use "system_command" SOMENTE quando o usurio pedir explicitamente para executar um comando no PowerShell/terminal (ex: "execute no PowerShell: ..."). Nunca use "system_command" para clculos, horrios, perguntas gerais ou respostas de conhecimento.
- Quando usar "system_command", o campo parameters.command deve ser um comando PowerShell vlido (no use sintaxe Linux como "date -d", "expr", etc.).
- Se faltar informao, use:
  "needs_clarification": true
  "clarifying_question": "pergunta curta"

INTENTS SUPORTADAS:
open_app, close_app, type_text, press_key, open_website, weather_report,
file_operation, project_manager, describe_screen, play_media, visual_navigate,
control_screen, video_analysis, chat, create_directory, scan_directory,
list_directory, get_file_info, system_command, set_timer, schedule_calendar, system_status,
search_web, fetch_web_content.
"""


def _ensure_cerebro_config() -> dict:
    # Mantido por compatibilidade, mas sem uso de APIs.
    return {"model": "disabled"}


def _ensure_prompt_json(default_prompt: str) -> str:
    # Garante prompt.json e retorna o prompt do sistema.
    if os.path.exists(PROMPT_JSON_PATH):
        try:
            with open(PROMPT_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("system_prompt"):
                    print(f"[CEREBRO] prompt.json carregado: {PROMPT_JSON_PATH}")
                    return str(data.get("system_prompt"))
        except Exception as e:
            print(f"[CEREBRO] Erro ao ler prompt.json: {e}")

    # Fallback para prompt.txt
    prompt_text = default_prompt
    if os.path.exists(PROMPT_PATH):
        try:
            with open(PROMPT_PATH, "r", encoding="utf-8") as f:
                prompt_text = f.read()
            print(f"[CEREBRO] prompt.txt carregado: {PROMPT_PATH}")
        except Exception as e:
            print(f"[CEREBRO] Erro ao ler prompt.txt: {e}")

    # Criar prompt.json se no existir ou invlido
    try:
        os.makedirs(os.path.dirname(PROMPT_JSON_PATH), exist_ok=True)
        with open(PROMPT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"system_prompt": prompt_text}, f, ensure_ascii=False, indent=2)
        print(f"[CEREBRO] prompt.json criado: {PROMPT_JSON_PATH}")
    except Exception as e:
        print(f"[CEREBRO] Falha ao criar prompt.json: {e}")

    return prompt_text


def init_cerebro_runtime() -> None:
    # Inicializa LLM principal via OpenRouter (fallback Groq).
    global SYSTEM_PROMPT, LLM_INITIALIZED, LLM_CLIENT, LLM_MODEL
    global LLM_CLIENT_GROQ, LLM_OPENROUTER_MODEL, LLM_OPENROUTER_KEY, LLM_GROQ_MODEL
    global LLM_OPENROUTER_SITE_URL, LLM_OPENROUTER_APP_NAME, LLM_OPENROUTER_DISABLE_ON_402
    global LLM_REASONING_EFFORT, LLM_INCLUDE_REASONING, LLM_REASONING_FORMAT
    global LLM_USE_PROMPT_CACHE, LLM_STRUCTURED_OUTPUTS, LLM_USE_TOOLS, LLM_TOOL_CHOICE
    if LLM_INITIALIZED:
        return
    load_dotenv()
    SYSTEM_PROMPT = _ensure_prompt_json(get_default_prompt())
    LLM_OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL") or "nousresearch/hermes-3-llama-3.1-405b:free"
    LLM_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY") or ""
    LLM_OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL") or ""
    LLM_OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME") or ""
    LLM_OPENROUTER_DISABLE_ON_402 = (
        (os.getenv("OPENROUTER_DISABLE_ON_402") or "false").lower() in {"1", "true", "yes", "on"}
    )
    LLM_GROQ_MODEL = os.getenv("GROQ_LLM_MODEL") or "gpt-oss-120b"
    LLM_MODEL = LLM_OPENROUTER_MODEL if LLM_OPENROUTER_KEY else LLM_GROQ_MODEL
    # Compound mode defaults (Reasoning + Structured Outputs + Tool Use + Prompt Caching)
    LLM_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT") or "high"
    LLM_REASONING_FORMAT = os.getenv("GROQ_REASONING_FORMAT") or "parsed"
    LLM_INCLUDE_REASONING = (os.getenv("GROQ_INCLUDE_REASONING") or "true").lower() in {"1", "true", "yes", "on"}
    LLM_USE_PROMPT_CACHE = (os.getenv("GROQ_USE_PROMPT_CACHE") or "true").lower() in {"1", "true", "yes", "on"}
    LLM_STRUCTURED_OUTPUTS = (os.getenv("GROQ_STRUCTURED_OUTPUTS") or "true").lower() in {"1", "true", "yes", "on"}
    LLM_USE_TOOLS = (os.getenv("GROQ_USE_TOOLS") or "true").lower() in {"1", "true", "yes", "on"}
    LLM_TOOL_CHOICE = os.getenv("GROQ_TOOL_CHOICE") or "auto"
    api_key = os.getenv("GROQ_API_KEY") or ""
    LLM_CLIENT_GROQ = Groq(api_key=api_key) if api_key else None
    LLM_CLIENT = True if LLM_OPENROUTER_KEY or LLM_CLIENT_GROQ else None
    LLM_INITIALIZED = True


def safe_json_parse(text: str) -> dict | None:
    """Parse JSON da resposta do LLM, removendo markdown se necessrio"""
    if not text:
        return None
    text = text.strip()

    # Remover blocos de cdigo markdown
    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        except: pass
    elif "```" in text:
        try:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()
        except: pass

    # Extrair JSON
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        json_str = text[start:end]
        return json.loads(json_str)
    except Exception as e:
        print(f" JSON parse error: {e}")
        return None


def _build_step(intent: str, parameters: dict | None = None, summary: str | None = None) -> dict:
    return {
        "step_id": str(uuid.uuid4()),
        "intent": intent,
        "parameters": parameters or {},
        "risk": "safe",
        "requires_confirmation": False,
        "summary": summary or f"Executar {intent}",
    }


def _build_envelope(
    plan: list | None = None,
    response: str | None = None,
    needs_clarification: bool = False,
    clarifying_question: str | None = None,
    goal: str | None = None,
) -> dict:
    raw = {
        "plan_id": str(uuid.uuid4()),
        "goal": goal or "",
        "needs_clarification": bool(needs_clarification),
        "clarifying_question": clarifying_question,
        "plan": plan or [],
        "response": response,
    }
    return asdict(normalize_plan(raw))


def _normalize_time_12h(text: str) -> str:
    import re
    def to_12h(match):
        hour = int(match.group(1))
        minute = match.group(2)
        second = match.group(3)
        suffix = match.group(4)
        if suffix:
            return match.group(0)
        if hour == 0:
            base = f"12:{minute}"
            if second:
                base += f":{second}"
            return f"{base} AM"
        if hour == 12:
            base = f"12:{minute}"
            if second:
                base += f":{second}"
            return f"{base} PM"
        if hour > 12:
            base = f"{hour - 12}:{minute}"
            if second:
                base += f":{second}"
            return f"{base} PM"
        base = f"{hour}:{minute}"
        if second:
            base += f":{second}"
        return f"{base} AM"

    pattern = r"\b([01]\d|2[0-3]):([0-5]\d)(::([0-5]\d))(\s(:am|pm|AM|PM))\b"
    return re.sub(pattern, to_12h, text)


def _sanitize_response_text(text: str | None) -> str | None:
    if not text:
        return text
    lowered = text.lower()
    if "test crono" in lowered or "test_crono" in lowered or "test-crono" in lowered:
        text = text.replace("test crono", "Crono").replace("Test Crono", "Crono").replace("TEST Crono", "Crono")
        text = text.replace("test_crono", "Crono").replace("Test_Crono", "Crono").replace("test-crono", "Crono")
    text = (
        text.replace("pronta", "pronto")
        .replace("Pronta", "Pronto")
        .replace("PRONTA", "PRONTO")
    )
    text = _normalize_time_12h(text)
    return text


def _strip_accents(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _format_memory_context(memory_block: dict | None) -> str:
    if not memory_block:
        return ""
    try:
        return json.dumps(memory_block, ensure_ascii=False, indent=2)
    except Exception:
        return str(memory_block)


def _maybe_answer_from_memory(user_text: str, memory_block: dict | None) -> dict | None:
    if not user_text or not memory_block:
        return None
    t = _strip_accents(user_text.lower())

    last_screen = memory_block.get("last_screen_description") or memory_block.get("recent_screen_analysis")
    last_image = memory_block.get("last_image_description")
    last_site = memory_block.get("last_opened_website")

    if any(k in t for k in ["ultima tela", "ultima imagem da tela", "tela anterior", "ultima visao"]):
        if last_screen:
            return _build_envelope(
                response=f"A ultima tela registrada foi: {last_screen}",
                goal="Responder sobre ultima tela"
            )
        return _build_envelope(
            response="Ainda nao tenho registro da ultima tela.",
            goal="Responder sobre ultima tela"
        )

    if any(k in t for k in ["ultima imagem", "imagem mais recente", "imagem recente"]):
        if last_image:
            return _build_envelope(
                response=f"A ultima imagem registrada foi: {last_image}",
                goal="Responder sobre ultima imagem"
            )
        return _build_envelope(
            response="Ainda nao tenho registro da ultima imagem.",
            goal="Responder sobre ultima imagem"
        )

    if any(k in t for k in ["ultimo site", "ultimo website", "ultima pagina", "ultimo link"]):
        if last_site:
            return _build_envelope(
                response=f"O ultimo site aberto foi: {last_site}",
                goal="Responder sobre ultimo site"
            )
        return _build_envelope(
            response="Ainda nao tenho registro do ultimo site aberto.",
            goal="Responder sobre ultimo site"
        )

    if "inscritos" in t and ("canal" in t or "youtube" in t):
        if last_screen:
            return _build_envelope(
                response=(
                    "Pelo que vi na ultima tela: "
                    f"{last_screen}. "
                    "Se o numero de inscritos nao estiver visivel, eu nao consigo confirmar."
                ),
                goal="Responder sobre inscritos do canal"
            )
        return _build_envelope(
            response="Ainda nao tenho registro da tela para verificar inscritos.",
            goal="Responder sobre inscritos do canal"
        )

    return None


def _cache_fingerprint(model: str, system_prompt: str, memory_context: str) -> str:
    import hashlib
    base = f"{model}||{system_prompt}||{memory_context}"
    return hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()


def _extract_cache_id(resp) -> str | None:
    if resp is None:
        return None
    try:
        if isinstance(resp, dict):
            return resp.get("cache_id")
        return getattr(resp, "cache_id", None)
    except Exception:
        return None


def _openrouter_headers() -> dict:
    headers = {
        "Authorization": f"Bearer {LLM_OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }
    if LLM_OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = LLM_OPENROUTER_SITE_URL
    if LLM_OPENROUTER_APP_NAME:
        headers["X-Title"] = LLM_OPENROUTER_APP_NAME
    return headers


def _call_openrouter(request_args: dict) -> dict:
    # Filter args for OpenRouter compatibility.
    allowed = {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "top_p",
        "stream",
        "stop",
        "response_format",
        "tools",
        "tool_choice",
    }
    body = {k: v for k, v in request_args.items() if k in allowed}

    def _post(model_id: str) -> dict:
        body["model"] = model_id
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=_openrouter_headers(),
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    try:
        return _post(LLM_OPENROUTER_MODEL)
    except requests.HTTPError as e:
        # Retry without :free suffix if model not found
        if e.response is not None and e.response.status_code == 404:
            if LLM_OPENROUTER_MODEL and ":free" in LLM_OPENROUTER_MODEL:
                retry_model = LLM_OPENROUTER_MODEL.split(":free", 1)[0]
                return _post(retry_model)
        raise


def _get_message_from_resp(resp):
    if isinstance(resp, dict):
        try:
            return resp.get("choices", [{}])[0].get("message", {}) or {}
        except Exception:
            return {}
    return resp.choices[0].message


def _structured_schema_prompt() -> str:
    return (
        "Return ONLY valid JSON with the schema:\n"
        "{\n"
        '  "intent": "string",\n'
        '  "parameters": "object",\n'
        '  "risk": "string",\n'
        '  "reasoning": "string",\n'
        '  "content": "string"\n'
        "}\n"
        "No markdown. No extra fields."
    )


def _validate_structured_output(obj: dict | None) -> tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "not a dict"
    required = ["intent", "parameters", "risk", "reasoning", "content"]
    for key in required:
        if key not in obj:
            return False, f"missing: {key}"
    if not isinstance(obj.get("parameters"), dict):
        return False, "parameters not object"
    return True, ""


def _normalize_structured_output(obj: dict, user_text: str) -> dict:
    intent = obj.get("intent") or "chat"
    params = obj.get("parameters") or {}
    risk = obj.get("risk") or "safe"
    reasoning = obj.get("reasoning") or ""
    content = obj.get("content") or ""
    if intent == "chat":
        env = _build_envelope(response=content, goal="Conversa")
        if reasoning:
            env["reasoning"] = reasoning
        return env
    step = _build_step(intent, params, summary=None)
    step["risk"] = risk
    env = _build_envelope(plan=[step], response=content if content else None, goal=user_text)
    if reasoning:
        env["reasoning"] = reasoning
    return env


def _build_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "open_app",
                "parameters": {
                    "type": "object",
                    "properties": {"app_name": {"type": "string"}},
                    "required": ["app_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_website",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "describe_screen",
                "parameters": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_web_content",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_durable_fact",
                "parameters": {
                    "type": "object",
                    "properties": {"fact": {"type": "string"}},
                    "required": ["fact"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_personal_data",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "graphic_art",
                "parameters": {
                    "type": "object",
                    "properties": {"prompt": {"type": "string"}},
                    "required": ["prompt"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "load_skills",
                "parameters": {
                    "type": "object",
                    "properties": {"skills": {"type": "array", "items": {"type": "string"}}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "multi_tool_use.parallel",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_uses": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "recipient_name": {"type": "string"},
                                    "parameters": {"type": "object"},
                                },
                                "required": ["recipient_name", "parameters"],
                            },
                        }
                    },
                    "required": ["tool_uses"],
                },
            },
        },
    ]


def _tool_calls_to_envelope(tool_calls: list, user_text: str) -> dict | None:
    if not tool_calls:
        return None
    steps = []
    for call in tool_calls:
        try:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            step = _build_step(name, args, summary=f"Executar {name}")
            steps.append(step)
        except Exception:
            continue
    if not steps:
        return None
    return _build_envelope(plan=steps, goal=user_text)


def _call_groq_with_fallback(request_args: dict):
    """
    Call Groq client with compatibility fallback when SDK doesn't support
    certain arguments (e.g., cache_control).
    """
    try:
        return LLM_CLIENT_GROQ.chat.completions.create(**request_args)
    except TypeError as e:
        msg = str(e)
        # Retry without prompt caching args if unsupported
        if "cache_control" in msg or "cache_id" in msg:
            request_args.pop("cache_control", None)
            request_args.pop("cache_id", None)
            try:
                return LLM_CLIENT_GROQ.chat.completions.create(**request_args)
            except Exception:
                raise
        # Retry without response_format if unsupported
        if "response_format" in msg:
            request_args.pop("response_format", None)
            return LLM_CLIENT_GROQ.chat.completions.create(**request_args)
        raise


def _call_llm(request_args: dict):
    global LLM_OPENROUTER_KEY, LLM_OPENROUTER_MODEL
    # Primary: OpenRouter if configured; fallback: Groq.
    if not LLM_OPENROUTER_KEY:
        # Permite reativar OpenRouter durante a sessao se a key foi limpa
        env_key = os.getenv("OPENROUTER_API_KEY") or ""
        if env_key:
            LLM_OPENROUTER_KEY = env_key
            if not LLM_OPENROUTER_MODEL:
                LLM_OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL") or "nousresearch/hermes-3-llama-3.1-405b:free"
    if LLM_OPENROUTER_KEY:
        try:
            return _call_openrouter(request_args)
        except Exception as e:
            # Disable OpenRouter for session on payment errors
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
            except Exception:
                status = None
            if status == 402 and LLM_OPENROUTER_DISABLE_ON_402:
                print("OpenRouter falhou: 402 Payment Required. Desativando OpenRouter nesta sesso.")
                LLM_OPENROUTER_KEY = ""
                LLM_OPENROUTER_MODEL = None
            else:
                print(f"OpenRouter falhou: {e}")
    if LLM_CLIENT_GROQ:
        try:
            request_args = dict(request_args)
            request_args["model"] = LLM_GROQ_MODEL
        except Exception:
            pass
        try:
            return _call_groq_with_fallback(request_args)
        except Exception as e:
            print(f"Groq LLM falhou: {e}")
            return None
    return None


def _format_duration_pt_br(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts: list[str] = []
    if hours:
        parts.append(f"{hours} hora" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minuto" + ("s" if minutes != 1 else ""))
    if not parts:
        parts.append(f"{seconds} segundo" + ("s" if seconds != 1 else ""))
    return " e ".join(parts)


def _maybe_handle_time_question(user_text: str) -> dict | None:
    """
    Fast local answers for time questions.

    This avoids the model generating a `system_command` for simple time math.
    """
    if not user_text or not user_text.strip():
        return None

    t = _strip_accents(user_text.lower()).strip()

    # If this is a timer/alarm request, let timer parser handle it.
    if any(k in t for k in ["temporizador", "timer", "cronometro", "alarme", "me avisa", "me lembre"]):
        return None

    # Avoid answering "time now" for weather questions
    if any(k in t for k in ["chuva", "chover", "vai chover", "clima", "temperatura", "previsao"]):
        return None

    # Current time
    if (
        "que horas" in t
        or t in {"horas", "hora", "horas sao", "hora sao", "hora e", "hora "}
        or (t.startswith("horas") and "sao" in t and len(t.split()) <= 3)
    ):
        from datetime import datetime
        now = datetime.now()
        now_12h = _normalize_time_12h(now.strftime("%H:%M"))
        return _build_envelope(response=f"Sao {now_12h}, senhor.", goal="Informar horario atual")

    # Time until noon
    if ("meio dia" in t or "meio-dia" in t or "12:00" in t) and any(
        k in t for k in ["quanto tempo", "quanto falta", "falta quanto", "ate", "para"]
    ):
        from datetime import datetime, timedelta
        now = datetime.now()
        noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if noon <= now:
            noon = noon + timedelta(days=1)
        delta = noon - now
        dur = _format_duration_pt_br(int(delta.total_seconds()))
        now_12h = _normalize_time_12h(now.strftime("%H:%M"))
        return _build_envelope(
            response=f"Agora sao {now_12h}. Faltam {dur} para meio-dia, senhor.",
            goal="Calcular tempo ate meio-dia",
        )

    # Time until midnight
    if ("meia noite" in t or "meia-noite" in t or "00:00" in t or "0:00" in t) and any(
        k in t for k in ["quanto tempo", "quanto falta", "falta quanto", "ate", "para"]
    ):
        from datetime import datetime, timedelta
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = midnight - now
        dur = _format_duration_pt_br(int(delta.total_seconds()))
        now_12h = _normalize_time_12h(now.strftime("%H:%M"))
        return _build_envelope(
            response=f"Agora sao {now_12h}. Faltam {dur} ate meia-noite, senhor.",
            goal="Calcular tempo ate meia-noite",
        )

    # Generic "how long until HH:MM / N horas" (ex: "quanto tempo falta para duas horas?")
    if any(k in t for k in ["quanto tempo", "quanto falta", "falta quanto", "falta para", "falta pra"]):
        import re
        from datetime import datetime, timedelta

        target_hour = None
        target_minute = 0

        # Explicit HH:MM / HhMM
        m = re.search(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b", t)
        if m:
            try:
                target_hour = int(m.group(1))
                target_minute = int(m.group(2))
            except Exception:
                target_hour = None

        # "duas horas", "14 horas"
        if target_hour is None:
            words_to_hour = {
                "uma": 1, "um": 1, "duas": 2, "dois": 2, "tres": 3, "quatro": 4, "cinco": 5,
                "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12
            }
            m = re.search(r"\b(\d{1,2}|uma|um|duas|dois|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze)\s+horas?\b", t)
            if m:
                token = m.group(1)
                if token.isdigit():
                    target_hour = int(token)
                else:
                    target_hour = words_to_hour.get(token)

        if target_hour is not None and 0 <= target_hour <= 23 and 0 <= target_minute <= 59:
            now = datetime.now()

            # Period disambiguation
            if ("da tarde" in t or "de tarde" in t or "da noite" in t) and target_hour < 12:
                target_hour += 12
            if ("da manha" in t or "de manha" in t or "madrugada" in t) and target_hour == 12:
                target_hour = 0

            candidates = []
            # If no explicit period and hour is 1..12, consider both AM and PM; choose nearest future.
            explicit_period = any(p in t for p in ["da tarde", "de tarde", "da noite", "da manha", "de manha", "madrugada"])
            if not explicit_period and 1 <= target_hour <= 12:
                candidates = [target_hour, (target_hour + 12) % 24]
            else:
                candidates = [target_hour]

            best_target = None
            best_delta = None
            for hh in candidates:
                target = now.replace(hour=hh, minute=target_minute, second=0, microsecond=0)
                if target <= now:
                    target = target + timedelta(days=1)
                delta = target - now
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best_target = target

            if best_target is not None and best_delta is not None:
                dur = _format_duration_pt_br(int(best_delta.total_seconds()))
                now_12h = _normalize_time_12h(now.strftime("%H:%M"))
                target_12h = _normalize_time_12h(best_target.strftime("%H:%M"))
                return _build_envelope(
                    response=f"Agora sao {now_12h}. Faltam {dur} para {target_12h}, senhor.",
                    goal="Calcular tempo ate horario informado",
                )

    return None


def _maybe_handle_timer_request(user_text: str) -> dict | None:
    """
    Local fast-path for simple timer requests.
    """
    if not user_text or not user_text.strip():
        return None

    raw = user_text.strip()
    t = _strip_accents(raw.lower())

    timer_markers = ["temporizador", "timer", "cronometro", "alarme", "me avisa", "me lembre"]
    if not any(k in t for k in timer_markers):
        return None

    # Status query should be handled by session memory (orchestrator), not by creating timer.
    if any(k in t for k in ["qual", "quais", "quanto falta", "falt", "resta", "ativo", "ativos", "tem", "existem"]) and any(
        k in t for k in ["timer", "temporizador", "alarme", "alarmes", "cronometro"]
    ):
        return None

    import re

    # If user wants to cancel/stop a timer, hand off to LLM (no fast-path).
    if any(k in t for k in ["apague", "cancele", "cancelar", "parar", "pare", "remova", "desative"]):
        return None

    # Timer by clock time (e.g. 8:30 / 8h30 / 8 e meia / 8h30pm).
    is_pm = any(k in t for k in ["pm", "p.m", "da tarde", "da noite"])
    is_am = any(k in t for k in ["am", "a.m", "da manha"])

    m_clock = re.search(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b", t)
    if m_clock:
        try:
            hh = int(m_clock.group(1))
            mm = int(m_clock.group(2))
            if is_pm and hh < 12:
                hh += 12
            if is_am and hh == 12:
                hh = 0
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return _build_envelope(
                    needs_clarification=False,
                    plan=[_build_step("set_timer", {"time_of_day": f"{hh:02d}:{mm:02d}"}, summary="Criar temporizador por horario")],
                    goal="Criar temporizador por horario",
                )
        except Exception:
            pass

    m_half = re.search(r"\b(\d{1,2})\s*e\s*meia\b", t)
    if m_half:
        try:
            hh = int(m_half.group(1))
            if is_pm and hh < 12:
                hh += 12
            if is_am and hh == 12:
                hh = 0
            if 0 <= hh <= 23:
                return _build_envelope(
                    needs_clarification=False,
                    plan=[_build_step("set_timer", {"time_of_day": f"{hh:02d}:30"}, summary="Criar temporizador por horario")],
                    goal="Criar temporizador por horario",
                )
        except Exception:
            pass

    # Natural phrases: "meio dia e meia/meio", "meia noite e meia/meio", "doze e meia/meio".
    if re.search(r"\b(meio[\s-]*dia|doze)\s*e\s*(meia|meio)\b", t):
        return _build_envelope(
            needs_clarification=False,
            plan=[_build_step("set_timer", {"time_of_day": "12:30"}, summary="Criar temporizador por horario")],
            goal="Criar temporizador por horario",
        )
    if re.search(r"\b(meia[\s-]*noite)\s*e\s*(meia|meio)\b", t):
        return _build_envelope(
            needs_clarification=False,
            plan=[_build_step("set_timer", {"time_of_day": "00:30"}, summary="Criar temporizador por horario")],
            goal="Criar temporizador por horario",
        )
    if re.search(r"\b(meio[\s-]*dia|doze)\b", t):
        return _build_envelope(
            needs_clarification=False,
            plan=[_build_step("set_timer", {"time_of_day": "12:00"}, summary="Criar temporizador por horario")],
            goal="Criar temporizador por horario",
        )
    if re.search(r"\b(meia[\s-]*noite)\b", t):
        return _build_envelope(
            needs_clarification=False,
            plan=[_build_step("set_timer", {"time_of_day": "00:00"}, summary="Criar temporizador por horario")],
            goal="Criar temporizador por horario",
        )

    hours = 0
    minutes = 0
    seconds = 0

    if "meia hora" in t:
        minutes += 30

    m = re.search(r"(\d+)\s*(h|hora|horas)\b", t)
    if m:
        try:
            hours = int(m.group(1))
        except Exception:
            hours = 0

    m = re.search(r"(\d+)\s*(m|min|minuto|minutos)\b", t)
    if m:
        try:
            minutes = int(m.group(1))
        except Exception:
            minutes = 0

    m = re.search(r"(\d+)\s*(s|seg|segundo|segundos)\b", t)
    if m:
        try:
            seconds = int(m.group(1))
        except Exception:
            seconds = 0

    total = hours * 3600 + minutes * 60 + seconds

    # If the user gave just a number, assume minutes.
    if total <= 0:
        m = re.search(r"\b(\d+)\b", t)
        if m and any(k in t for k in ["min", "minuto", "minutos", "temporizador", "timer"]):
            try:
                total = int(m.group(1)) * 60
            except Exception:
                total = 0

    if total <= 0:
        return _build_envelope(
            needs_clarification=True,
            clarifying_question="Por quanto tempo? Exemplo: 5 minutos, 1 hora.",
            goal="Criar temporizador",
        )

    title = ""
    m = re.search(r"\b(?:para|pra|pro)\s+(.+)$", t)
    if m:
        candidate = m.group(1).strip(" .,!:;")
        if not re.match(r"^\d{1,2}\s*[:h]\s*\d{2}$", candidate):
            title = candidate

    params = {"duration_seconds": int(total), "system_notification": True}
    if title:
        params["title"] = title

    step = _build_step("set_timer", params, summary="Criar temporizador")
    return _build_envelope(plan=[step], goal="Criar temporizador")


def _normalize_llm_response(parsed: dict | None, user_text: str) -> dict | None:
    if not parsed:
        return None

    # New plan schema already
    if "plan" in parsed or "plan_id" in parsed:
        return asdict(normalize_plan(parsed))

    # Legacy actions array
    if "actions" in parsed and isinstance(parsed.get("actions"), list):
        plan_steps = []
        for action in parsed.get("actions") or []:
            if not isinstance(action, dict):
                continue
            intent = action.get("intent") or ""
            if intent:
                plan_steps.append(_build_step(intent, action.get("parameters") or {}, action.get("summary")))
        response = parsed.get("text") or parsed.get("response")
        return _build_envelope(plan=plan_steps, response=response, goal=parsed.get("goal") or user_text)

    # Legacy intent-based response
    if "intent" in parsed:
        intent = parsed.get("intent") or "chat"
        params = parsed.get("parameters") or {}
        if intent == "chat":
            response = parsed.get("text") or parsed.get("content") or parsed.get("response")
            return _build_envelope(response=response, goal="Conversa")
        step = _build_step(intent, params, parsed.get("summary"))
        response = parsed.get("text") if parsed.get("text") else None
        needs_clarification = bool(parsed.get("needs_clarification", False))
        clarifying_question = parsed.get("clarifying_question") or (parsed.get("text") if needs_clarification else None)
        return _build_envelope(
            plan=[step] if not needs_clarification else [],
            response=response if not needs_clarification else None,
            needs_clarification=needs_clarification,
            clarifying_question=clarifying_question,
            goal=parsed.get("goal") or user_text,
        )

    # Content-only response
    content = parsed.get("text") or parsed.get("content") or parsed.get("response")
    if content:
        return _build_envelope(response=content, goal="Conversa")

    return None


def _needs_reasoning_hint(user_text: str) -> bool:
    if not user_text:
        return False
    t = _strip_accents(user_text.lower())
    keywords = [
        "por que", "porque", "explique", "explicar", "passo a passo", "raciocinio",
        "logica", "planejar", "planejamento", "como voce chegou", "como chegou",
        "memoria", "lembra", "ultima tela", "ultima imagem", "ultimo site",
        "calcule", "calcular", "resolver", "analise", "analisa", "analisar",
        "programacao", "codigo"
    ]
    return any(k in t for k in keywords)


def _is_web_search_request(user_text: str) -> bool:
    if not user_text or not user_text.strip():
        return False
    t = _strip_accents(user_text.lower())
    explicit = [
        "pesquise", "pesquisar", "procure", "procurar", "busque", "buscar",
        "na internet", "na web", "pesquisa na web", "pesquisa na internet",
        "pesquise na web", "pesquise na internet", "procure na web", "procure na internet"
    ]
    if any(k in t for k in explicit):
        return True

    # Heuristica para perguntas tipicamente "agora/hoje"
    live_markers = ["agora", "hoje", "neste momento", "nesse momento", "atual"]
    price_markers = ["preco", "cotacao", "quanto esta", "valor do", "taxa de cambio"]
    if any(k in t for k in live_markers) and any(k in t for k in price_markers):
        return True

    return False


def _maybe_handle_web_search_request(user_text: str) -> dict | None:
    if not _is_web_search_request(user_text):
        return None

    query = re.sub(
        r"\b(pesquise|pesquisar|procure|procurar|busque|buscar|na internet|na web)\b",
        "",
        user_text,
        flags=re.IGNORECASE,
    ).strip(" :,-")
    if not query:
        query = user_text.strip()
    if not query:
        return None

    step = _build_step("search_web", {"query": query}, summary="Pesquisar na web")
    return _build_envelope(plan=[step], goal=f"Pesquisar: {query}")


def _maybe_handle_weather_request(user_text: str) -> dict | None:
    if not user_text or not user_text.strip():
        return None
    raw = user_text.strip()
    t = _strip_accents(raw.lower())

    weather_markers = [
        "clima", "tempo", "previsao", "chuva", "chover", "temperatura",
        "graus", "frio", "quente"
    ]
    if not any(k in t for k in weather_markers):
        return None

    # Avoid conflicting with explicit time-of-day questions
    if "que horas" in t or "qual a hora" in t:
        return None

    city = None
    import re
    m = re.search(r"\bem\s+([a-zA-ZÀ-ÿ\s]+)", raw, flags=re.IGNORECASE)
    if m:
        city = m.group(1).strip(" .,!:;")

    # Common cities fallback
    if not city:
        city_map = {
            "sao paulo": "Sao Paulo",
            "rio de janeiro": "Rio de Janeiro",
            "brasilia": "Brasilia",
            "salvador": "Salvador",
            "fortaleza": "Fortaleza",
            "belo horizonte": "Belo Horizonte",
        }
        for k, v in city_map.items():
            if k in _strip_accents(raw.lower()):
                city = v
                break

    if not city:
        city = "Sao Paulo"

    step = _build_step("weather_report", {"city": city}, summary=f"Consultar clima em {city}")
    return _build_envelope(plan=[step], goal=f"Clima em {city}")


def _maybe_handle_playlist_request(user_text: str) -> dict | None:
    if not user_text or not user_text.strip():
        return None
    raw = user_text.strip()
    t = _strip_accents(raw.lower())
    if "playlist" not in t and "lista de reproducao" not in t:
        return None

    # Open/play intent
    if any(k in t for k in ["abrir", "abre", "abra", "tocar", "toca", "play"]):
        name = ""
        marker = "playlist" if "playlist" in t else "lista de reproducao"
        tail = t.split(marker, 1)[1].strip() if marker in t else ""
        tail = re.sub(r"^(do|da|de|dos|das)\s+", "", tail).strip()
        for stop in ["pra mim", "para mim", "agora", "por favor"]:
            if stop in tail:
                tail = tail.split(stop, 1)[0].strip()
        if tail and tail not in {"aquela", "essa", "esta"}:
            name = tail
        if not name:
            return _build_envelope(
                needs_clarification=True,
                clarifying_question="Qual playlist voce quer abrir",
                goal="Abrir playlist",
            )
        step = _build_step("play_media", {"name": name}, summary=f"Abrir playlist {name}")
        return _build_envelope(plan=[step], goal=f"Abrir playlist {name}")

    return None


def detect_intent_by_keywords(user_text: str) -> tuple[str | None, dict]:
    """
    Sistema de fallback: detecta intent por keywords quando Trinity falha.
    Retorna (intent, parameters) ou (None, {})
    """
    text_lower = user_text.lower()

    def _keyword_match(keyword: str) -> bool:
        kw = (keyword or "").strip().lower()
        if not kw:
            return False
        if re.fullmatch(r"[\w\s]+", kw, flags=re.IGNORECASE):
            pattern = r"(<!\w)" + re.escape(kw).replace(r"\ ", r"\s+") + r"(!\w)"
            return re.search(pattern, text_lower, flags=re.IGNORECASE) is not None
        return kw in text_lower
    # Cancelar timer
    if any(k in text_lower for k in ["timer", "temporizador", "cronometro", "cronmetro"]) and any(
        k in text_lower for k in ["apague", "cancele", "cancelar", "pare", "parar", "remova", "desative"]
    ):
        return ("cancel_timer", {})

    # Playlist fast-path (avoid open_app fallback for playlist commands)
    if "playlist" in text_lower or "lista de reproducao" in text_lower:
        params = {}
        if any(k in text_lower for k in [
            "criar playlist", "crie a playlist", "crie playlist", "nova playlist",
            "salvar playlist", "salve a playlist", "salve playlist"
        ]):
            params["action"] = "create"
        name = None
        for marker in ["playlist", "lista de reproducao"]:
            if marker in text_lower:
                tail = text_lower.split(marker, 1)[1].strip()
                tail = re.sub(r"^(do|da|de|dos|das)\s+", "", tail)
                for stop in ["por favor", "pra mim", "para mim", "agora"]:
                    if stop in tail:
                        tail = tail.split(stop, 1)[0].strip()
                if tail:
                    name = tail
                    break
        if name:
            params["name"] = name
        return ("play_media", params)


    # Mapeamento de keywords -> intent
    intent_patterns = {
        # Viso e tela (PRIORIDADE MXIMA)
        "describe_screen": [
            "o que voc v", "o que v", "que voc v", "v na tela",
            "descreve a tela", "descreva a tela", "descrever a tela",
            "o que tem na tela", "que tem na tela", "o que est na tela",
            "analisa a tela", "analise a tela", "analisar a tela",
            "veja a tela", "veja isso", "olha a tela", "olhe a tela",
            "me diz o que", "me diga o que", "pode ver"
        ],

        # Abrir apps
        "open_app": [
            "abra o", "abre o", "abrir o", "abre", "abra", "open",
            "iniciar", "inicia o", "inicia", "roda o", "rode o", "execute o",
            "liga o", "ligue o"
        ],

        # Fechar apps
        "close_app": [
            "fecha o", "feche o", "fechar o", "fecha", "feche", "close",
            "encerra o", "encerrar o", "encerra", "mata o", "mate o",
            "desliga o", "desligue o"
        ],

        # Websites
        "open_website": [
            "youtube.com", "google.com", "facebook.com", "instagram.com",
            "twitter.com", "github.com", "abra o site", "abre o site",
            "vai para o site", "acessa o site", "acesse"
        ],
        "search_web": [
            "pesquise", "pesquisar", "procure", "procurar", "busque", "buscar",
            "na internet", "na web", "pesquisa na internet", "pesquisa na web"
        ],
        "fetch_web_content": [
            "resuma esse link", "resume esse link", "resuma esta pagina", "resuma essa pagina",
            "analise esta url", "analise essa url", "leia esta url", "leia esse link"
        ],

        # Comandos do sistema (PowerShell)
        "system_command": [
            "executa o comando", "execute o comando", "rodar comando", "rode o comando",
            "no powershell", "powershell:"
        ],

        # Temporizador
        "set_timer": [
            "temporizador", "timer", "cronometro", "cronmetro", "me avisa em", "me lembre em"
        ],

        # Calendrio
        "schedule_calendar": [
            "agenda", "agendar", "calendario", "calendrio", "marcar no calendario", "marcar no calendrio", "compromisso"
        ],

        # Status do sistema (CPU/RAM/Disco)
        "system_status": [
            "uso de cpu", "uso da cpu", "cpu", "processador",
            "uso de ram", "uso da ram", "memoria ram", "memria ram", "ram",
            "uso do disco", "disco cheio", "armazenamento",
            "status do sistema", "desempenho do sistema", "monitoramento"
        ],

        # Controle de tela (clique, movimento)
        "control_screen": [
            "clica aqui", "clique aqui", "click here",
            "mova o mouse", "moves o mouse", "arrasta", "arraste"
        ],

        # Navegao visual (clica em boto especfico)
        "visual_navigate": [
            "clica no", "clique no", "clica em", "clique em",
            "aperta o", "aperte o", "pressiona o", "pressione o"
        ],

        # Digitar texto
        "type_text": [
            "digite", "digita", "escreva", "escreve", "type"
        ],

        # Clima (apenas quando for sobre clima mesmo, no tempo genrico)
        "weather_report": [
            "qual o clima", "como est o clima", "previso do tempo",
            "vai chover", "temperatura", "graus", "est frio", "est quente",
            "tempo em", "clima em", "weather in", "tempo hoje", "clima hoje"
        ],

        # Arquivos
        "file_operation": [
            "cria arquivo", "criar arquivo", "delete arquivo", "apaga arquivo",
            "cria pasta", "criar pasta", "delete pasta", "apaga pasta",
            "lista arquivo", "listar arquivo", "l arquivo", "ler arquivo"
        ],

        # Projetos
        "project_manager": [
            "comea projeto", "comear projeto", "inicia projeto", "iniciar projeto",
            "novo projeto", "criar projeto", "encerra projeto", "sair projeto"
        ],

        # Msica/Media
        "play_media": [
            "toca", "tocar", "play", "msica", "musica", "som"
        ],
        "remember_note": [
            "lembra de", "lembre de", "memoriza", "memorizar", "guarda isso",
            "guarde isso", "salva isso", "salvar isso", "anota", "anote"
        ],
        "search_personal_data": [
            "o que voce lembra", "o que você lembra", "o que sabe sobre",
            "me lembra sobre", "buscar na memoria", "buscar na memória",
            "procura nas minhas notas", "procure nas minhas notas"
        ],
        "clear_popups": [
            "limpa popup", "limpar popups", "fechar popups", "sumir popups",
            "limpa alertas", "limpar alertas", "fechar alertas"
        ],
    }

    # Verificar cada padro (ordem importa!)
    for intent, keywords in intent_patterns.items():
        for keyword in keywords:
            if _keyword_match(keyword):
                print(f"[KEYWORD] detectada: '{keyword}' -> intent={intent}")

                # Extrair parmetros bsicos
                params = {}

                if intent == "describe_screen":
                    # Sem parmetros necessrios
                    params = {}

                elif intent == "open_app":
                    params = {}
                    # Tenta extrair nome do app (expandido com mais apps)
                    apps_map = {
                        # Navegadores
                        "chrome": ["chrome", "google chrome"],
                        "firefox": ["firefox", "fire fox", "mozilla"],
                        "edge": ["edge", "microsoft edge"],
                        "opera": ["opera", "opera gx", "operagx"],
                        "brave": ["brave"],

                        # IDEs e editores
                        "vscode": ["vscode", "vs code", "visual studio code", "code"],
                        "pycharm": ["pycharm"],
                        "sublime": ["sublime", "sublime text"],
                        "notepad": ["notepad", "bloco de notas", "notepad++"],

                        # Comunicao
                        "discord": ["discord"],
                        "slack": ["slack"],
                        "teams": ["teams", "microsoft teams"],
                        "zoom": ["zoom"],
                        "whatsapp": ["whatsapp", "whats"],
                        "telegram": ["telegram"],

                        # Mdia
                        "spotify": ["spotify"],
                        "vlc": ["vlc"],

                        # Outros
                        "terminal": ["terminal", "cmd", "prompt"],
                        "explorer": ["explorer", "explorador", "arquivos"],
                    }

                    for app_key, app_variations in apps_map.items():
                        for variation in app_variations:
                            if variation in text_lower:
                                params = {"app_name": app_key}
                                break
                        if params:
                            break

                elif intent == "close_app":
                    params = {}
                    # Mesma lgica para fechar apps
                    apps_map = {
                        "chrome": ["chrome", "google chrome"],
                        "firefox": ["firefox", "fire fox", "mozilla"],
                        "edge": ["edge", "microsoft edge"],
                        "opera": ["opera", "opera gx", "operagx", "navegador"],
                        "brave": ["brave"],
                        "vscode": ["vscode", "vs code", "visual studio code", "code"],
                        "discord": ["discord"],
                        "spotify": ["spotify"],
                        "whatsapp": ["whatsapp", "whats"],
                        "telegram": ["telegram"],
                        "notepad": ["notepad", "bloco de notas"],
                    }

                    for app_key, app_variations in apps_map.items():
                        for variation in app_variations:
                            if variation in text_lower:
                                params = {"app_name": app_key}
                                break
                        if params:
                            break

                elif intent == "open_website":
                    params = {}
                    # Tenta extrair URL
                    urls = ["youtube.com", "google.com", "facebook.com", "instagram.com", "twitter.com", "github.com"]
                    for url in urls:
                        if url in text_lower:
                            params = {"url": url}
                            break

                    # Se no achou URL especfica mas tem palavras-chave
                    if not params and any(x in text_lower for x in ["site", "pgina", "acessa"]):
                        # Tentar extrair domnio
                        words = text_lower.split()
                        for word in words:
                            if ".com" in word or ".br" in word or ".org" in word:
                                params = {"url": word}
                                break

                elif intent == "search_web":
                    cleaned = re.sub(
                        r"\b(pesquise|pesquisar|procure|procurar|busque|buscar|na internet|na web)\b",
                        "",
                        user_text,
                        flags=re.IGNORECASE,
                    ).strip(" :,-")
                    params = {"query": cleaned or user_text}

                elif intent == "fetch_web_content":
                    params = {}
                    m = re.search(r"(https://\S+)", user_text, flags=re.IGNORECASE)
                    if m:
                        params["url"] = m.group(1).rstrip(".,;)")
                    else:
                        words = re.split(r"\s+", user_text.strip())
                        for word in words:
                            token = word.strip(".,;)")
                            if any(token.lower().startswith(prefix) for prefix in ("www.",)) or \
                               any(token.lower().endswith(suffix) for suffix in (".com", ".com.br", ".org", ".net", ".io", ".dev", ".ai", ".gov", ".edu")):
                                if not token.lower().startswith(("http://", "https://")):
                                    token = "https://" + token
                                params["url"] = token
                                break
                    if params.get("url"):
                        lower = user_text.lower()
                        marker = "sobre "
                        if marker in lower:
                            idx = lower.index(marker) + len(marker)
                            q = user_text[idx:].strip()
                            if q:
                                params["question"] = q

                elif intent == "system_command":
                    cmd = user_text
                    if "powershell:" in text_lower:
                        cmd = user_text.split("powershell:", 1)[1].strip()
                    elif "executa o comando" in text_lower:
                        cmd = user_text.split("executa o comando", 1)[1].strip()
                    elif "execute o comando" in text_lower:
                        cmd = user_text.split("execute o comando", 1)[1].strip()
                    elif "rodar comando" in text_lower:
                        cmd = user_text.split("rodar comando", 1)[1].strip()
                    elif "rode o comando" in text_lower:
                        cmd = user_text.split("rode o comando", 1)[1].strip()
                    params = {"command": cmd.strip()} if cmd else {}

                elif intent == "set_timer":
                    # Best-effort parse for durations. Prefer local fast-path in get_llm_output.
                    hours = 0
                    minutes = 0
                    seconds = 0

                    mh = re.search(r"(\d+)\s*(h|hora|horas)\b", text_lower)
                    if mh:
                        try:
                            hours = int(mh.group(1))
                        except Exception:
                            hours = 0
                    mm = re.search(r"(\d+)\s*(m|min|minuto|minutos)\b", text_lower)
                    if mm:
                        try:
                            minutes = int(mm.group(1))
                        except Exception:
                            minutes = 0
                    ms = re.search(r"(\d+)\s*(s|seg|segundo|segundos)\b", text_lower)
                    if ms:
                        try:
                            seconds = int(ms.group(1))
                        except Exception:
                            seconds = 0

                    total = hours * 3600 + minutes * 60 + seconds
                    if total > 0:
                        params = {"duration_seconds": total, "system_notification": True}

                elif intent == "schedule_calendar":
                    # Keep it minimal here; the LLM should provide ISO datetime.
                    title = None
                    if ":" in user_text:
                        title = user_text.split(":")[-1].strip()
                    if title:
                        params = {"title": title}
                    lower_u = text_lower
                    if any(k in lower_u for k in ["todo dia", "diariamente", "cada dia"]):
                        params["recurrence_freq"] = "DAILY"
                    elif any(k in lower_u for k in ["toda semana", "semanalmente", "cada semana"]):
                        params["recurrence_freq"] = "WEEKLY"
                    elif any(k in lower_u for k in ["todo mes", "todo mês", "mensalmente", "cada mes", "cada mês"]):
                        params["recurrence_freq"] = "MONTHLY"
                    mr = re.search(r"(\d+)\s*(min|minuto|minutos)\s*(antes|de antecedencia|de antecedência)", lower_u)
                    if mr:
                        try:
                            params["reminder_minutes"] = int(mr.group(1))
                        except Exception:
                            pass

                elif intent == "visual_navigate":
                    # Tenta extrair alvo do clique
                    target_words = text_lower.replace("clica no ", "").replace("clique no ", "")
                    target_words = target_words.replace("clica em ", "").replace("clique em ", "")
                    target_words = target_words.replace("aperta o ", "").replace("aperte o ", "")
                    params = {"target": target_words.strip()}

                elif intent == "weather_report":
                    # Tenta extrair cidade
                    cities = ["so paulo", "rio de janeiro", "braslia", "salvador", "fortaleza", "belo horizonte"]
                    for city in cities:
                        if city in text_lower:
                            params = {"city": city.title()}
                            break
                    if not params:
                        params = {"city": "So Paulo"}  # default

                elif intent == "play_media":
                    # Tenta extrair query
                    query = text_lower.replace("toca ", "").replace("tocar ", "").replace("play ", "")
                    params = {"query": query.strip()}

                elif intent == "remember_note":
                    note = text_lower
                    for prefix in ["lembra de", "lembre de", "memoriza", "memorizar", "guarda isso", "guarde isso", "salva isso", "salvar isso", "anota", "anote"]:
                        if prefix in note:
                            note = note.split(prefix, 1)[1].strip()
                            break
                    params = {"note": note} if note else {}

                elif intent == "search_personal_data":
                    cleaned = text_lower
                    for prefix in [
                        "o que voce lembra", "o que você lembra", "o que sabe sobre",
                        "me lembra sobre", "buscar na memoria", "buscar na memória",
                        "procura nas minhas notas", "procure nas minhas notas"
                    ]:
                        if prefix in cleaned:
                            cleaned = cleaned.split(prefix, 1)[1].strip()
                            break
                    params = {"query": cleaned or user_text}

                return (intent, params)

    # Nenhuma keyword detectada
    return (None, {})


def _fallback_intent_from_text(user_text: str) -> dict | None:
    intent, params = detect_intent_by_keywords(user_text)
    if not intent:
        return None
    params = params or {}
    if intent == "open_app" and not params.get("app_name"):
        return _build_envelope(
            needs_clarification=True,
            clarifying_question="Qual aplicao voc deseja abrir",
            goal=user_text,
        )
    if intent == "play_media" and not params.get("name"):
        return _build_envelope(
            needs_clarification=True,
            clarifying_question="Qual o nome da playlist",
            goal=user_text,
        )
    step = _build_step(intent, params)
    return _build_envelope(plan=[step], goal=user_text)

def normalize_trinity_response(parsed: dict, user_text: str) -> dict:
    """
    Normaliza resposta do Trinity que pode vir em formatos diferentes.
    Inclui sistema de fallback por deteco de keywords.
    """
    if not parsed:
        return None

    # Formato correto j (mas verifica se intent no  chat quando deveria ser ao)
    if "intent" in parsed and "text" in parsed:
        intent = parsed.get("intent")
        text = parsed.get("text")
        actions = parsed.get("actions", [])

        # NOVO: Se Trinity retornou 'actions' array, use a primeira ao!
        if actions and isinstance(actions, list) and len(actions) > 0:
            first_action = actions[0]
            action_intent = first_action.get("intent")
            action_params = first_action.get("parameters", {})

            print(f" Trinity retornou actions: {action_intent} com params {action_params}")

            # Usar a ao ao invs do chat
            # IMPORTANTE: Mantm o texto para falar ANTES de executar
            return {
                "intent": action_intent,
                "parameters": action_params,
                "needs_clarification": False,
                "text": text,  # Mantm texto do Trinity (fala antes da ao)
                "keep_text": True,  # Flag para no remover o texto depois
                "memory_update": parsed.get("memory_update")
            }

        # Se Trinity disse "chat" E j tem texto, confie nele (no sobrescreva)
        if intent == "chat" and text:
            # MAS: verifica se tem keywords bvias de ao
            detected_intent, detected_params = detect_intent_by_keywords(user_text)

            # Se detectou ao clara (no weather/media), sobrescreve
            # Aes claras: open_app, close_app, describe_screen, brightness, volume, etc.
            excluded_intents = ["weather_report", "play_media"]

            if detected_intent and detected_intent not in excluded_intents:
                print(f" Trinity disse 'chat' mas detectei ao clara '{detected_intent}' - sobrescrevendo")
                return {
                    "intent": detected_intent,
                    "parameters": detected_params,
                    "needs_clarification": False,
                    "text": text,  # Mantm texto do Trinity
                    "keep_text": True,  # Fala antes de executar
                    "memory_update": parsed.get("memory_update")
                }

            print(" Trinity retornou chat com texto - confiando na resposta")
            return parsed

        # Se Trinity disse "chat" mas NO tem texto, pode ser uma ao
        if intent == "chat" and not text:
            detected_intent, detected_params = detect_intent_by_keywords(user_text)
            if detected_intent:
                print(f" Trinity disse 'chat' sem texto - detectei '{detected_intent}' por keywords")
                parsed["intent"] = detected_intent
                parsed["parameters"] = detected_params
                parsed["text"] = None

        return parsed

    # Formato OpenAI (role/content)
    if "role" in parsed and "content" in parsed:
        print(" Normalizando formato OpenAI -> Crono")
        # Tenta detectar intent por keywords
        detected_intent, detected_params = detect_intent_by_keywords(user_text)

        return {
            "intent": detected_intent or "chat",
            "parameters": detected_params,
            "needs_clarification": False,
            "text": parsed["content"] if not detected_intent else None,
            "memory_update": parsed.get("memory_update")
        }

    # Detectar se  apenas metadados (username, message, time, etc)
    metadata_keys = {"username", "message", "time", "date", "timezone", "user", "timestamp"}
    if metadata_keys.intersection(parsed.keys()):
        print(" Trinity retornou metadados - detectando intent por keywords")
        detected_intent, detected_params = detect_intent_by_keywords(user_text)

        return {
            "intent": detected_intent or "chat",
            "parameters": detected_params,
            "needs_clarification": False,
            "text": "E a, no que posso ajudar" if not detected_intent else None,
            "memory_update": parsed.get("memory_update")
        }

    # Formato com "content" mas sem "role"
    if "content" in parsed and "text" not in parsed:
        print(" Normalizando 'content' -> 'text'")
        parsed["text"] = parsed["content"]

        if "intent" not in parsed or parsed.get("intent") == "chat":
            # Tenta detectar intent
            detected_intent, detected_params = detect_intent_by_keywords(user_text)
            if detected_intent:
                print(f" Detectei intent '{detected_intent}' por keywords")
                parsed["intent"] = detected_intent
                parsed["parameters"] = detected_params
                parsed["text"] = None  # Aes no tm texto
            else:
                parsed["intent"] = "chat"
        return parsed

    # Se tem text mas no tem intent
    if "text" in parsed and "intent" not in parsed:
        print(" Adicionando intent")
        detected_intent, detected_params = detect_intent_by_keywords(user_text)
        parsed["intent"] = detected_intent or "chat"
        if detected_intent:
            parsed["parameters"] = detected_params
            parsed["text"] = None  # Aes no tm texto
        return parsed

    # Fallback: tenta extrair qualquer texto
    text_content = (
        parsed.get("text") or
        parsed.get("content") or
        parsed.get("response") or
        parsed.get("reply")
    )

    # ltima tentativa de detectar intent
    detected_intent, detected_params = detect_intent_by_keywords(user_text)

    print(f" Fallback: intent={detected_intent or 'chat'}")
    return {
        "intent": detected_intent or "chat",
        "parameters": detected_params or parsed.get("parameters", {}),
        "needs_clarification": False,
        "text": text_content if not detected_intent else None,
        "memory_update": parsed.get("memory_update")
    }


def get_llm_output(
    user_text: str,
    memory_block: dict = None,
    reasoning_effort: str | None = None,
    include_reasoning: bool | None = None,
    reasoning_format: str | None = None,
    allow_reasoning_hint: bool = True,
    use_prompt_cache: bool | None = None,
    structured_outputs: bool | None = None,
    use_tools: bool | None = None,
    tool_choice: str | None = None,
) -> dict:
    global LLM_USE_PROMPT_CACHE
    """Processa entrada do usuario e retorna um plano estruturado."""
    print(f"LLM recebeu: '{user_text}'")

    if not user_text or not user_text.strip():
        return _build_envelope(response="Desculpe, nao entendi.", goal="Conversa")

    # Local fast-paths
    # Timer before time-question to avoid collisions such as:
    # "faz um timer pra meio dia" being interpreted as "quanto falta para meio-dia".
    local_timer = _maybe_handle_timer_request(user_text)
    if local_timer:
        return local_timer
    
    local_time = _maybe_handle_time_question(user_text)
    if local_time:
        return local_time

    local_web = _maybe_handle_web_search_request(user_text)
    if local_web:
        return local_web

    local_weather = _maybe_handle_weather_request(user_text)
    if local_weather:
        return local_weather

    local_playlist = _maybe_handle_playlist_request(user_text)
    if local_playlist:
        return local_playlist

    memory_answer = _maybe_answer_from_memory(user_text, memory_block)
    if memory_answer:
        return memory_answer

    if not LLM_INITIALIZED:
        init_cerebro_runtime()

    if not LLM_CLIENT:
        detected_intent, detected_params = detect_intent_by_keywords(user_text)
        if detected_intent:
            if detected_intent in {"open_app", "close_app"} and not detected_params.get("app_name"):
                return _build_envelope(
                    needs_clarification=True,
                    clarifying_question="Qual o nome exato do aplicativo",
                    goal=user_text,
                )
            step = _build_step(detected_intent, detected_params)
            return _build_envelope(plan=[step], goal=user_text)
        return _build_envelope(response="IA principal indisponivel. Posso executar acoes diretas se voce pedir.", goal="Conversa")

    memory_context = _format_memory_context(memory_block)

    user_prompt = f"""User message: "{user_text}" """

    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if memory_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "CONTEXT_MEMORY (use this to answer):\n"
                        f"{memory_context}\n"
                        "If memory is missing, say so clearly."
                    ),
                }
            )
        if allow_reasoning_hint and _needs_reasoning_hint(user_text):
            messages.append(
                {
                    "role": "system",
                    "content": "Use reasoning to explain your plan before responding when helpful.",
                }
            )
        use_structured = LLM_STRUCTURED_OUTPUTS if structured_outputs is None else bool(structured_outputs)
        use_tooling = LLM_USE_TOOLS if use_tools is None else bool(use_tools)
        if use_structured:
            messages.append(
                {
                    "role": "system",
                    "content": _structured_schema_prompt(),
                }
            )
        messages.append({"role": "user", "content": user_prompt})

        reffort = reasoning_effort or LLM_REASONING_EFFORT
        if allow_reasoning_hint and _needs_reasoning_hint(user_text):
            reffort = "high"
        rformat = reasoning_format or LLM_REASONING_FORMAT
        rinclude = LLM_INCLUDE_REASONING if include_reasoning is None else bool(include_reasoning)
        # Avoid using include_reasoning with reasoning_format together
        if rformat and rformat != "hidden":
            rinclude = False

        use_cache = LLM_USE_PROMPT_CACHE if use_prompt_cache is None else bool(use_prompt_cache)
        cache_args = {}
        if use_cache:
            global _LLM_CACHE_ID, _LLM_CACHE_FINGERPRINT
            fp = _cache_fingerprint(LLM_MODEL, SYSTEM_PROMPT or "", memory_context or "")
            if not _LLM_CACHE_ID or _LLM_CACHE_FINGERPRINT != fp:
                cache_args["cache_control"] = "create"
            else:
                cache_args["cache_control"] = "use"
                cache_args["cache_id"] = _LLM_CACHE_ID

        request_args = dict(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1200,
            reasoning_effort=reffort,
        )
        # Mutually exclusive: include_reasoning OR reasoning_format
        if rformat and rformat != "hidden":
            request_args["reasoning_format"] = rformat
        else:
            request_args["include_reasoning"] = rinclude
        if use_tooling:
            request_args["tools"] = _build_tool_definitions()
            request_args["tool_choice"] = tool_choice or LLM_TOOL_CHOICE
        # Avoid json mode with tool calling (Groq constraint)
        if use_structured and not use_tooling:
            request_args["response_format"] = {"type": "json_object"}
        request_args.update(cache_args)

        try:
            resp = _call_llm(request_args)
        except TypeError as e:
            if "cache_control" in str(e) or "cache_id" in str(e):
                # Disable caching for this session if unsupported
                LLM_USE_PROMPT_CACHE = False
            raise
        if resp is None:
            raise RuntimeError("LLM indisponvel")
        if use_cache:
            cache_id = _extract_cache_id(resp)
            fp = _cache_fingerprint(LLM_MODEL, SYSTEM_PROMPT or "", memory_context or "")
            if cache_id:
                _LLM_CACHE_ID = cache_id
                _LLM_CACHE_FINGERPRINT = fp
        msg = _get_message_from_resp(resp)
        if isinstance(msg, dict):
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning")
            tool_calls = msg.get("tool_calls")
        else:
            content = msg.content or ""
            reasoning = getattr(msg, "reasoning", None)
            tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            tool_env = _tool_calls_to_envelope(tool_calls, user_text)
            if tool_env:
                if reasoning:
                    tool_env["reasoning"] = reasoning
                return tool_env
        parsed = safe_json_parse(content) if use_structured else safe_json_parse(content)
        normalized = None
        if use_structured:
            if parsed:
                ok, err = _validate_structured_output(parsed)
                if ok:
                    normalized = _normalize_structured_output(parsed, user_text)
                else:
                    fallback = _fallback_intent_from_text(user_text)
                    if fallback:
                        return fallback
                    return _build_envelope(
                        response="Recebi uma resposta invalida do modelo. Pode repetir",
                        goal="Resposta invalida"
                    )
            else:
                fallback = _fallback_intent_from_text(user_text)
                if fallback:
                    return fallback
                return _build_envelope(
                    response="Nao consegui validar a resposta do modelo. Pode repetir",
                    goal="Resposta invalida"
                )
        if normalized is None:
            normalized = _normalize_llm_response(parsed, user_text)
        if normalized and "response" in normalized:
            normalized["response"] = _sanitize_response_text(normalized.get("response"))
        # Se a sada estruturada no trouxe resposta para chat, tenta um fallback em texto puro
        try:
            if normalized:
                resp_text = normalized.get("response")
                plan = normalized.get("plan") or []
                only_chat = False
                if plan and isinstance(plan, list):
                    intents = [p.get("intent") for p in plan if isinstance(p, dict)]
                    only_chat = all(i == "chat" for i in intents if i)
                if (not resp_text or not str(resp_text).strip()) and (only_chat or not plan):
                    # Requisio rpida sem JSON/schema
                    plain_args = dict(request_args)
                    plain_args.pop("response_format", None)
                    plain_args.pop("tools", None)
                    plain_args.pop("tool_choice", None)
                    # Remove schema prompt se existir
                    plain_messages = [
                        m for m in messages
                        if not (m.get("role") == "system" and "Return ONLY valid JSON" in (m.get("content") or ""))
                    ]
                    plain_messages.append(
                        {
                            "role": "system",
                            "content": "Responda diretamente em texto simples, sem JSON.",
                        }
                    )
                    plain_args["messages"] = plain_messages
                    plain_args["max_tokens"] = 600
                    plain_args["temperature"] = 0.3
                    plain_resp = _call_llm(plain_args)
                    if plain_resp:
                        plain_msg = _get_message_from_resp(plain_resp)
                        if isinstance(plain_msg, dict):
                            plain_content = plain_msg.get("content") or ""
                        else:
                            plain_content = plain_msg.content or ""
                        if plain_content and plain_content.strip():
                            normalized = _build_envelope(response=plain_content.strip(), goal="Conversa")
        except Exception:
            pass
        if normalized is None:
            normalized = _build_envelope(response=content, goal="Conversa")
        if reasoning:
            normalized["reasoning"] = reasoning
        if normalized:
            return normalized
    except Exception as e:
        print(f"Groq LLM falhou: {e}")

    detected_intent, detected_params = detect_intent_by_keywords(user_text)
    if detected_intent:
        if detected_intent in {"open_app", "close_app"} and not detected_params.get("app_name"):
            return _build_envelope(
                needs_clarification=True,
                clarifying_question="Qual o nome exato do aplicativo",
                goal=user_text,
            )
        step = _build_step(detected_intent, detected_params)
        return _build_envelope(plan=[step], goal=user_text)

    return _build_envelope(response="Desculpe, tive um problema. Tenta de novo", goal="Conversa")
