import json
import os
import re
import threading
from collections import deque
from datetime import datetime

import requests

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class AutonomousMemoryManager:
    """
    Sistema de memria autnomo em 3 camadas:
    1) Anlise rpida (pattern matching)
    2) Anlise profunda (LLM/OpenRouter)
    3) Consolidao peridica (a cada 5 interações)
    """

    def __init__(self, base_dir: str | None = None, filename: str = "cerebro.json"):
        self.base_dir = base_dir or os.getcwd()
        self.path = os.path.join(self.base_dir, filename)
        self.memoria_lp = self._carregar_memoria()
        self.contexto_curto = []
        self.buffer_analise = []
        self._queue = deque()
        self._queue_lock = threading.Lock()
        self._worker = None
        self._enabled = (os.getenv("AUTOMEM_ENABLED") or "true").lower() in {"1", "true", "yes", "on"}

        self._model = os.getenv("AUTOMEM_MODEL") or os.getenv("OPENROUTER_MODEL") or "nousresearch/hermes-3-llama-3.1-405b:free"
        self._api_key = os.getenv("OPENROUTER_API_KEY") or ""
        self._site_url = os.getenv("OPENROUTER_SITE_URL") or ""
        self._app_name = os.getenv("OPENROUTER_APP_NAME") or "Cronos"

        self._client = None
        if OpenAI and self._api_key:
            try:
                self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=self._api_key)
            except Exception:
                self._client = None

    def _log(self, msg: str):
        print(f"[MEM] {msg}")

    def _carregar_memoria(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                self._log(f" Falha ao carregar memria: {e}")
        return {
            "usuario": {},
            "preferencias": {},
            "contexto_pessoal": {},
            "historico_eventos": [],
            "relacionamentos": {},
            "metas_objetivos": {},
        }

    def _salvar_memoria(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.memoria_lp, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f" Falha ao salvar memria: {e}")

    # ============================================
    # CAMADA 1: ANLISE RPIDA
    # ============================================
    def analisar_mensagem_rapido(self, mensagem_usuario: str) -> list[dict]:
        if not mensagem_usuario:
            return []

        msg = mensagem_usuario.strip()
        msg_lower = msg.lower()
        infos = []

        def _add(cat, chave, valor, relevancia="media"):
            infos.append(
                {
                    "categoria": cat,
                    "chave": chave,
                    "valor": valor,
                    "relevancia": relevancia,
                }
            )

        # Nome
        m = re.search(r"\b(meu nome (e|)|me chamo|pode me chamar de)\s+(.+)", msg, re.IGNORECASE)
        if m:
            nome = m.group(3).strip(" .,!:;")
            if nome:
                _add("usuario", "nome", nome, "alta")

        # Localizao
        m = re.search(r"\b(moro em|sou de|vivo em)\s+(.+)", msg, re.IGNORECASE)
        if m:
            local = m.group(2).strip(" .,!:;")
            if local:
                _add("contexto_pessoal", "localizacao", local, "media")

        # Profisso
        m = re.search(r"\b(trabalho como|atuo como|sou)\s+(.+)", msg, re.IGNORECASE)
        if m and "sou" not in msg_lower[:6]:
            prof = m.group(2).strip(" .,!:;")
            if prof:
                _add("usuario", "profissao", prof, "media")

        # Idade
        m = re.search(r"\btenho\s+(\d{1,3})\s+anos\b", msg_lower)
        if m:
            _add("usuario", "idade", m.group(1), "media")

        # Email
        m = re.search(r"\bmeu e-mail\s+(e|)\s*([^\s,;]+)", msg_lower)
        if m:
            _add("usuario", "email", m.group(2), "alta")

        # Telefone
        m = re.search(r"\b(meu telefone|meu celular)\s+(e|)\s*(.+)", msg_lower)
        if m:
            _add("usuario", "telefone", m.group(3).strip(" .,!:;"), "alta")

        # Preferncias
        prefs = ["gosto de", "adoro", "amo", "prefiro", "favorito"]
        if any(p in msg_lower for p in prefs):
            _add("preferencias", "gostos", msg, "media")

        # Averses
        avs = ["odeio", "nao gosto", "no gosto", "detesto"]
        if any(a in msg_lower for a in avs):
            _add("preferencias", "aversoes", msg, "media")

        return infos

    def _apply_infos(self, infos: list[dict], fonte: str = "rapida"):
        if not infos:
            return
        def _norm(v: str) -> str:
            v = str(v or "").lower().strip()
            v = re.sub(r"\s+", " ", v)
            v = v.replace("usurio", "usuario")
            return v
        for info in infos:
            categoria = info.get("categoria")
            chave = info.get("chave")
            valor = info.get("valor")
            relevancia = info.get("relevancia", "media")
            if not categoria or not chave or not valor:
                continue
            if categoria not in self.memoria_lp:
                self.memoria_lp[categoria] = {} if categoria != "historico_eventos" else []

            # Dedup simples por valor j existente na categoria
            if categoria != "historico_eventos" and isinstance(self.memoria_lp.get(categoria), dict):
                existing = self.memoria_lp[categoria]
                norm_val = _norm(valor)
                if any(
                    _norm(v.get("valor", "") if isinstance(v, dict) else v) == norm_val
                    for v in existing.values()
                ):
                    continue
                # no sobrescrever chave existente com mesmo valor
                if chave in existing and isinstance(existing[chave], dict):
                    if _norm(existing[chave].get("valor", "")) == norm_val:
                        continue

            entry = {
                "valor": valor,
                "relevancia": relevancia,
                "timestamp": datetime.now().isoformat(),
                "fonte": fonte,
            }
            if categoria == "historico_eventos":
                if isinstance(self.memoria_lp[categoria], list):
                    self.memoria_lp[categoria].append(entry)
            else:
                if not isinstance(self.memoria_lp[categoria], dict):
                    self.memoria_lp[categoria] = {}
                self.memoria_lp[categoria][chave] = entry
            self._log(f" Memria salva: {categoria}.{chave} = {valor}")
        self._salvar_memoria()

    # ============================================
    # CAMADA 2: ANLISE PROFUNDA (LLM)
    # ============================================
    def _call_openrouter(self, messages: list[dict], temperature: float = 0.1) -> str:
        if self._client:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._app_name:
            headers["X-Title"] = self._app_name
        def _post(model_id: str) -> str:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={"model": model_id, "messages": messages, "temperature": temperature},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        try:
            return _post(self._model)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                if self._model and ":free" in self._model:
                    retry_model = self._model.split(":free", 1)[0]
                    return _post(retry_model)
            raise

    def _parse_json(self, text: str) -> dict:
        if not text:
            return {}
        raw = text.strip()
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def analisar_com_llm(self, msg_user: str, msg_assistant: str) -> dict:
        if not self._enabled or not self._api_key:
            return {"informacoes": []}
        prompt = f"""Voce um sistema de memria de longo prazo. Analise esta conversa e extraia APENAS informaes importantes que devem ser lembradas permanentemente sobre o usurio.

CONVERSA:
Usurio: {msg_user}
Assistente: {msg_assistant}

INSTRUES:
1. Extraia APENAS fatos objetivos e importantes sobre o usurio
2. Ignore conversas casuais ou triviais
3. Identifique: preferncias, dados pessoais, contexto importante, metas, relacionamentos
4. Responda APENAS em JSON no formato abaixo

IMPORTANTE: Se no houver nada importante para salvar, retorne um JSON vazio: {{"informacoes": []}}

FORMATO DE RESPOSTA (JSON):
{{
  "informacoes": [
    {{
      "categoria": "usuario|preferencias|contexto_pessoal|relacionamentos|metas_objetivos",
      "chave": "nome_descritivo",
      "valor": "informao objetiva",
      "relevancia": "alta|media|baixa",
      "timestamp": "opcional - quando o evento aconteceu"
    }}
  ],
  "reasoning": "Por que essas informaes so importantes (breve)"
}}
"""
        try:
            content = self._call_openrouter([{"role": "user", "content": prompt}], temperature=0.1)
            return self._parse_json(content) or {"informacoes": []}
        except Exception as e:
            self._log(f" Erro ao analisar com LLM: {e}")
            return {"informacoes": []}

    # ============================================
    # CAMADA 3: CONSOLIDAO PERIDICA
    # ============================================
    def consolidar_memorias(self) -> dict | None:
        if not self._enabled or not self._api_key:
            return None
        if len(self.buffer_analise) < 5:
            return None
        contexto_buffer = "\n\n".join(
            [f"User: {b['user']}\nAssistant: {b['assistant']}" for b in self.buffer_analise[-5:]]
        )
        prompt = f"""Voc  um sistema de consolidao de memrias. Analise estas interaes recentes e identifique padres, preferncias implcitas ou informaes importantes que no foram capturadas individualmente.

HISTRICO RECENTE:
{contexto_buffer}

MEMRIAS ATUAIS:
{json.dumps(self.memoria_lp, indent=2, ensure_ascii=False)}

TAREFAS:
1. Identifique padres de comportamento ou preferncias
2. Atualize informaes se houver contradies
3. Extraia contexto que s fica claro com mltiplas mensagens
4. Sugira novas categorias de memria se relevante

Responda em JSON:
{{
  "novos_fatos": [...],
  "atualizacoes": [...],
  "padroes_identificados": [...],
  "reasoning": "..."
}}

Se no houver nada relevante: {{"novos_fatos": [], "atualizacoes": [], "padroes_identificados": []}}"""
        try:
            content = self._call_openrouter([{"role": "user", "content": prompt}], temperature=0.2)
            data = self._parse_json(content)
            return data
        except Exception as e:
            self._log(f" Erro na consolidao: {e}")
            return None

    # ============================================
    # FLUXO PRINCIPAL
    # ============================================
    def processar_mensagem_rapida(self, msg_user: str):
        infos = self.analisar_mensagem_rapido(msg_user)
        if infos:
            self._log(" Deteco rpida de memria")
            self._apply_infos(infos, fonte="rapida")

    def processar_interacao(self, msg_user: str, msg_assistant: str):
        if not msg_user or not msg_assistant:
            return
        # Evita anlise profunda de respostas triviais (reduz rudo), mas mantm contexto curto
        t = msg_user.strip().lower()
        skip_deep = t in {"sim", "nao", "no", "ok", "okay", "beleza", "uhum", "aham", "fala"} or len(t) < 5
        # Atualiza contexto curto (rolling window)
        self.contexto_curto.append({"role": "user", "content": msg_user})
        self.contexto_curto.append({"role": "assistant", "content": msg_assistant})
        if len(self.contexto_curto) > 20:
            self.contexto_curto = self.contexto_curto[-20:]

        if skip_deep:
            return

        # Buffer para consolidao
        self.buffer_analise.append(
            {"user": msg_user, "assistant": msg_assistant, "timestamp": datetime.now().isoformat()}
        )

        # Enfileira anlise profunda em background
        with self._queue_lock:
            self._queue.append((msg_user, msg_assistant))
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._analysis_worker, daemon=True)
                self._worker.start()

    def _analysis_worker(self):
        while True:
            with self._queue_lock:
                if not self._queue:
                    return
                msg_user, msg_assistant = self._queue.popleft()

            analise = self.analisar_com_llm(msg_user, msg_assistant)
            infos = analise.get("informacoes") if isinstance(analise, dict) else []
            if infos:
                self._log(" Anlise profunda detectou memrias")
                self._apply_infos(infos, fonte="llm")

            if len(self.buffer_analise) >= 5:
                consolidacao = self.consolidar_memorias()
                if isinstance(consolidacao, dict):
                    novos = consolidacao.get("novos_fatos") or []
                    atualizacoes = consolidacao.get("atualizacoes") or []
                    padroes = consolidacao.get("padroes_identificados") or []
                    if novos:
                        self._log(f" Consolidao: {len(novos)} novos fatos")
                        self._apply_infos(novos, fonte="consolidacao")
                    if atualizacoes:
                        self._log(f" Consolidao: {len(atualizacoes)} atualizaes")
                        self._apply_infos(atualizacoes, fonte="consolidacao")
                    if padroes:
                        if "contexto_pessoal" not in self.memoria_lp or not isinstance(
                            self.memoria_lp["contexto_pessoal"], dict
                        ):
                            self.memoria_lp["contexto_pessoal"] = {}
                        self.memoria_lp["contexto_pessoal"]["padroes"] = padroes
                        self._salvar_memoria()
                    self.buffer_analise = []

    def formatar_memorias(self) -> str:
        if not self.memoria_lp:
            return "Nenhuma informao salva ainda."
        texto = []
        for categoria, dados in self.memoria_lp.items():
            if not dados:
                continue
            texto.append(f"\n{categoria.upper().replace('_', ' ')}:")
            if isinstance(dados, dict):
                for chave, info in dados.items():
                    if isinstance(info, dict):
                        valor = info.get("valor", "")
                        relevancia = info.get("relevancia", "")
                        texto.append(f"- {chave}: {valor} ({relevancia})")
                    else:
                        texto.append(f"- {chave}: {info}")
            elif isinstance(dados, list):
                for item in dados[-5:]:
                    texto.append(f"- {item}")
        return "\n".join(texto) if texto else "Nenhuma informao salva ainda."
