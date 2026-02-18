import asyncio
import html
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

from llm import get_llm_output


@dataclass
class AdaWebResult:
    success: bool
    text: str
    error: str = ""
    elapsed_sec: float = 0.0


class AdaWebAgent:
    """
    Web layer extracted for Cronos using HTTP + existing LLM stack (Groq/OpenRouter).
    """

    def __init__(self):
        self.timeout = 20
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.serpapi_key = (
            os.getenv("SERPAPI_API_KEY")
            or os.getenv("SERP_API_KEY")
            or ""
        ).strip()

    def check_ready(self) -> tuple[bool, str]:
        if self.serpapi_key:
            return True, ""
        return True, "SERPAPI_API_KEY ausente; usando fallback DuckDuckGo"

    def _http_get(self, url: str) -> str:
        resp = requests.get(
            url,
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        )
        resp.raise_for_status()
        return resp.text or ""

    @staticmethod
    def _clean_html_to_text(raw_html: str) -> str:
        if not raw_html:
            return ""
        text = re.sub(r"(is)<script.*>.*</script>", " ", raw_html)
        text = re.sub(r"(is)<style.*>.*</style>", " ", text)
        text = re.sub(r"(is)<noscript.*>.*</noscript>", " ", text)
        text = re.sub(r"(s)<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _decode_ddg_redirect(link: str) -> str:
        try:
            parsed = urlparse(link)
            qs = parse_qs(parsed.query or "")
            uddg = qs.get("uddg", [])
            if uddg:
                return unquote(uddg[0])
        except Exception:
            pass
        return link

    def _search_sync(self, query: str, limit: int = 5) -> list[dict]:
        # Prefer SerpAPI when API key is configured.
        if self.serpapi_key:
            try:
                return self._search_sync_serpapi(query=query, limit=limit)
            except Exception:
                # Soft fallback keeps web search available even if SerpAPI is unstable.
                pass

        q = quote_plus(query)
        url = f"https://duckduckgo.com/html/q={q}"
        html_doc = self._http_get(url)
        matches = re.findall(
            r'(is)<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*)</a>',
            html_doc,
        )
        snippets = re.findall(r'(is)<a[^>]*class="result__snippet"[^>]*>(.*)</a>', html_doc)
        results = []
        for idx, (link, title_html) in enumerate(matches[: max(1, limit)]):
            title = self._clean_html_to_text(title_html)
            snippet = self._clean_html_to_text(snippets[idx]) if idx < len(snippets) else ""
            decoded = self._decode_ddg_redirect(link)
            results.append({"title": title, "url": decoded, "snippet": snippet, "source": "duckduckgo"})
        return results

    def _search_sync_serpapi(self, query: str, limit: int = 5) -> list[dict]:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "api_key": self.serpapi_key,
                "hl": "pt-BR",
                "gl": "br",
                "num": max(1, min(int(limit), 10)),
            },
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        )
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        organic = data.get("organic_results") or []
        results = []
        for item in organic[: max(1, limit)]:
            title = str(item.get("title") or "").strip()
            link = str(item.get("link") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if title or link or snippet:
                results.append({"title": title, "url": link, "snippet": snippet, "source": "serpapi"})
        return results

    def _summarize_with_llm(self, prompt: str) -> str:
        try:
            out = get_llm_output(
                user_text=prompt,
                memory_block={},
                include_reasoning=False,
                reasoning_format="hidden",
                reasoning_effort="low",
                allow_reasoning_hint=False,
                structured_outputs=False,
                use_tools=False,
                tool_choice=None,
                use_prompt_cache=False,
            )
            text = (out or {}).get("response") or ""
            return str(text).strip()
        except Exception:
            return ""

    @staticmethod
    def _strip_urls(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"https://\S+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _format_brl(value: float) -> str:
        inteiro = int(value)
        centavos = int(round((value - inteiro) * 100))
        return f"R$ {inteiro},{centavos:02d}"

    def _extract_price_answer(self, query: str, results: list[dict]) -> str:
        if not results:
            return ""

        q = (query or "").lower()
        need_gas_price = any(token in q for token in ["botij", "gás", "gas", "glp"])
        raw_values = []
        for item in results:
            blob = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                ]
            )
            matches = re.findall(r"R\$\s*(\d{1,3}(:\.\d{3})*(:,\d{2})|\d+(:[.,]\d{2}))", blob, flags=re.IGNORECASE)
            for m in matches:
                normalized = m.replace(".", "").replace(",", ".")
                try:
                    raw_values.append(float(normalized))
                except Exception:
                    pass

        if not raw_values:
            return ""

        # Heuristica para gás 13kg: evitar preços claramente fora da faixa.
        if need_gas_price:
            filtered = [v for v in raw_values if 70.0 <= v <= 200.0]
            values = filtered or raw_values
        else:
            values = raw_values

        values = sorted(values)
        low = values[0]
        high = values[-1]
        if low == high:
            return f"Pelos resultados encontrados, o valor está em torno de {self._format_brl(low)}."
        return (
            "Pelos resultados encontrados, o preço está na faixa de "
            f"{self._format_brl(low)} a {self._format_brl(high)}."
        )

    async def search_web(self, query: str, user_request: str | None = None, timeout_sec: int = 180) -> AdaWebResult:
        started = time.time()
        try:
            results = await asyncio.wait_for(asyncio.to_thread(self._search_sync, query, 5), timeout=timeout_sec)
            if not results:
                return AdaWebResult(
                    success=True,
                    text="Nao encontrei resultados relevantes na web para essa consulta.",
                    elapsed_sec=max(0.0, time.time() - started),
                )

            lines = []
            for i, item in enumerate(results, start=1):
                lines.append(
                    f"{i}. {item.get('title','')}\nURL: {item.get('url','')}\nResumo: {item.get('snippet','')}"
                )
            context = "\n\n".join(lines)
            prompt = (
                "Com base nos resultados abaixo, responda em portugues-BR de forma direta ao pedido do usuario. "
                "Nao liste links, nao inclua URLs e nao descreva sites. "
                "Se houver valores, diga apenas a faixa de preco e um resumo curto.\n\n"
                f"PEDIDO ORIGINAL: {user_request or query}\n"
                f"CONSULTA: {query}\n\nRESULTADOS:\n{context}"
            )
            summary = await asyncio.to_thread(self._summarize_with_llm, prompt)
            summary = self._strip_urls(summary)
            if summary:
                return AdaWebResult(success=True, text=summary, elapsed_sec=max(0.0, time.time() - started))

            extracted = self._extract_price_answer(user_request or query, results)
            if extracted:
                return AdaWebResult(success=True, text=extracted, elapsed_sec=max(0.0, time.time() - started))

            if not summary:
                bullets = []
                for r in results[:3]:
                    title = str(r.get("title", "")).strip()
                    snippet = str(r.get("snippet", "")).strip()
                    text = f"{title}. {snippet}".strip(". ")
                    if text:
                        bullets.append(f"- {text}")
                summary = "Resumo dos resultados: " + " ".join(bullets) if bullets else "Encontrei resultados, mas sem dados objetivos para responder com precisão."
            return AdaWebResult(success=True, text=summary, elapsed_sec=max(0.0, time.time() - started))
        except Exception as e:
            return AdaWebResult(success=False, text="", error=str(e), elapsed_sec=max(0.0, time.time() - started))

    async def fetch_web_content(self, url: str, question: str | None = None, timeout_sec: int = 180) -> AdaWebResult:
        started = time.time()
        clean_url = str(url or "").strip()
        if not re.match(r"^https://", clean_url, flags=re.IGNORECASE):
            clean_url = "https://" + clean_url
        try:
            raw_html = await asyncio.wait_for(asyncio.to_thread(self._http_get, clean_url), timeout=timeout_sec)
            content = self._clean_html_to_text(raw_html)
            if not content:
                return AdaWebResult(
                    success=True,
                    text="Consegui abrir a URL, mas nao encontrei texto legivel na pagina.",
                    elapsed_sec=max(0.0, time.time() - started),
                )
            clipped = content[:12000]
            if question:
                prompt = (
                    "Responda em portugues-BR com base no conteudo da pagina abaixo.\n\n"
                    f"URL: {clean_url}\n"
                    f"PERGUNTA: {question}\n\n"
                    f"CONTEUDO:\n{clipped}"
                )
            else:
                prompt = (
                    "Resuma em portugues-BR o conteudo principal da pagina abaixo em no maximo 8 linhas.\n\n"
                    f"URL: {clean_url}\n\n"
                    f"CONTEUDO:\n{clipped}"
                )
            summary = await asyncio.to_thread(self._summarize_with_llm, prompt)
            if not summary:
                summary = clipped[:800]
            return AdaWebResult(success=True, text=summary, elapsed_sec=max(0.0, time.time() - started))
        except Exception as e:
            return AdaWebResult(success=False, text="", error=str(e), elapsed_sec=max(0.0, time.time() - started))


_ADA_WEB_AGENT = None


def get_ada_web_agent() -> AdaWebAgent:
    global _ADA_WEB_AGENT
    if _ADA_WEB_AGENT is None:
        _ADA_WEB_AGENT = AdaWebAgent()
    return _ADA_WEB_AGENT
