import re
import unicodedata
from typing import Optional, Tuple


_VOCAB = {
    "replacements": [],
    "context_rules": [],
}


def _ensure_vocab() -> dict:
    return _VOCAB


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    text = "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    # Normalize punctuation to spaces and collapse
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_word(word: str) -> str:
    if not word:
        return ""
    word = word.strip().lower()
    word = "".join(
        ch for ch in unicodedata.normalize("NFD", word)
        if unicodedata.category(ch) != "Mn"
    )
    return word


def _replacement_exists(data: dict, src: str, dst: str) -> bool:
    src_n = _normalize(src)
    dst_n = _normalize(dst)
    for item in data.get("replacements", []):
        if _normalize(str(item.get("from", ""))) == src_n and _normalize(str(item.get("to", ""))) == dst_n:
            return True
    return False


def add_replacement(src: str, dst: str) -> bool:
    data = _ensure_vocab()
    if _replacement_exists(data, src, dst):
        return False
    data["replacements"].append({"from": src, "to": dst})
    _VOCAB.update(data)
    return True


def add_context_rule(src: str, dst: str, context: list[str]) -> None:
    data = _ensure_vocab()
    data["context_rules"].append({"from": src, "to": dst, "context": context})
    _VOCAB.update(data)


def _build_variant_map(replacements: list[dict]) -> dict[str, str]:
    variant_map: dict[str, str] = {}
    for item in replacements:
        src = str(item.get("from", "")).strip()
        dst = str(item.get("to", "")).strip()
        if not dst:
            continue
        if src:
            src_norm = _normalize(src)
            if src_norm:
                variant_map[src_norm] = dst
        # Also allow exact targets to match themselves
        dst_norm = _normalize(dst)
        if dst_norm:
            variant_map.setdefault(dst_norm, dst)
    return variant_map


def _max_phrase_tokens(variant_map: dict[str, str]) -> int:
    max_tokens = 1
    for key in variant_map.keys():
        if " " in key:
            max_tokens = max(max_tokens, len(key.split()))
    return min(max_tokens, 5)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"\w+|[^\w]+", text, flags=re.UNICODE)


def _apply_replacements(text: str, replacements: list[dict]) -> str:
    """
    Apply exact replacements while preserving original punctuation/casing.
    Supports join/split variants like "si a" -> "crono".
    """
    variant_map = _build_variant_map(replacements)
    if not variant_map or not text:
        return text

    tokens = _tokenize(text)
    if not tokens:
        return text

    word_positions = [i for i, t in enumerate(tokens) if re.match(r"^\w+$", t)]
    words = [tokens[i] for i in word_positions]
    norm_words = [_normalize_word(w) for w in words]

    max_span = _max_phrase_tokens(variant_map)
    used_word = [False] * len(words)

    i = 0
    while i < len(words):
        if used_word[i]:
            i += 1
            continue

        matched = False
        for span in range(max_span, 1, -1):
            if i + span > len(words):
                continue
            if any(used_word[i:i + span]):
                continue
            chunk_words = norm_words[i:i + span]
            chunk_space = " ".join(chunk_words)
            chunk_join = "".join(chunk_words)
            target = variant_map.get(chunk_space) or variant_map.get(chunk_join)
            if target:
                # Replace token range from first word token to last word token
                start_token = word_positions[i]
                end_token = word_positions[i + span - 1]
                tokens[start_token] = target
                for t_idx in range(start_token + 1, end_token + 1):
                    tokens[t_idx] = ""
                for k in range(i, i + span):
                    used_word[k] = True
                matched = True
                break
        if matched:
            i += 1
            continue

        # Single-word replacement
        w_norm = norm_words[i]
        target = variant_map.get(w_norm)
        if target:
            tokens[word_positions[i]] = target
            used_word[i] = True
        i += 1

    return "".join(tokens)


def _apply_context_rules(text: str, rules: list[dict]) -> str:
    out = text
    normalized_text = _normalize(text)
    for item in rules:
        src = str(item.get("from", "")).strip()
        dst = str(item.get("to", "")).strip()
        ctx = item.get("context") or []
        if not src or not ctx:
            continue
        ctx_norm = [_normalize(c) for c in ctx if c]
        if any(c and c in normalized_text for c in ctx_norm):
            src_norm = _normalize(src)
            if not src_norm:
                continue
            pattern = r"(<!\w)" + re.escape(src) + r"(!\w)"
            out = re.sub(pattern, dst, out, flags=re.IGNORECASE)
            normalized_text = _normalize(out)
    return out


def _fuzzy_replace_words(text: str, replacements: list[dict]) -> str:
    try:
        from difflib import SequenceMatcher
    except Exception:
        return text

    tokens = _tokenize(text)
    if not tokens:
        return text

    word_positions = [i for i, t in enumerate(tokens) if re.match(r"^\w+$", t)]
    words = [tokens[i] for i in word_positions]
    if not words:
        return text

    variant_map = _build_variant_map(replacements)
    variants = [v for v in variant_map.keys() if " " not in v]
    if not variants:
        return text

    def best_match(word: str):
        best = None
        best_score = 0.0
        for v in variants:
            if len(word) < 4 and len(v) < 4:
                continue
            if abs(len(word) - len(v)) > 2:
                continue
            score = SequenceMatcher(None, word, v).ratio()
            if score > best_score:
                best_score = score
                best = v
        return best, best_score

    for idx, w in enumerate(words):
        w_norm = _normalize_word(w)
        if w_norm in variant_map:
            tokens[word_positions[idx]] = variant_map[w_norm]
            continue
        v, score = best_match(w_norm)
        if v and score >= 0.88:
            tokens[word_positions[idx]] = variant_map[v]

    return "".join(tokens)


def correct_text(text: str) -> str:
    data = _ensure_vocab()
    if not text:
        return text
    out = text
    out = _apply_context_rules(out, data.get("context_rules", []))
    out = _apply_replacements(out, data.get("replacements", []))
    out = _fuzzy_replace_words(out, data.get("replacements", []))
    return out


def maybe_handle_vocab_command(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detecta comandos de vocabulário.
    Retorna (handled, response).
    """
    t = text.strip()

    # quando eu falar X, entenda Y
    m = re.search(r"quando eu (falar|disser|digitar) (.+)[, ]+entenda (.+)$", t, flags=re.IGNORECASE)
    if m:
        src = m.group(2).strip().strip("\"'")
        dst = m.group(3).strip().strip("\"'")
        if src and dst:
            add_replacement(src, dst)
            return True, f"Ok. Vou entender '{src}' como '{dst}'."

    # quando eu falar X com/ no contexto Y, entenda Z
    m = re.search(r"quando eu (falar|disser|digitar) (.+) (com|no contexto) (.+)[, ]+entenda (.+)$", t, flags=re.IGNORECASE)
    if m:
        src = m.group(2).strip().strip("\"'")
        ctx = m.group(4).strip()
        dst = m.group(5).strip().strip("\"'")
        context_list = [c.strip() for c in re.split(r"[,;]", ctx) if c.strip()]
        if src and dst and context_list:
            add_context_rule(src, dst, context_list)
            return True, f"Ok. Em contexto {', '.join(context_list)}, vou entender '{src}' como '{dst}'."

    return False, None


def import_variants_block(text: str) -> tuple[int, int]:
    """
    Importa blocos no formato:
      alvo: var1, var2, var3
    Retorna (adicionados, ignorados)
    """
    data = _ensure_vocab()
    added = 0
    skipped = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Remove bullets or numbering
        line = line.lstrip("-*•").strip()
        if not line:
            continue
        # Support separators like ":" "=>" "->" "="
        parts = re.split(r"\s*(:=>|->|:|=)\s*", line, maxsplit=1)
        if len(parts) != 2:
            continue
        target, variants = parts[0], parts[1]
        target = target.strip().strip("\"'")
        if not target or not variants:
            continue
        for var in re.split(r"[;,|]", variants):
            v = var.strip().strip("\"'")
            if not v:
                continue
            if _replacement_exists(data, v, target):
                skipped += 1
                continue
            data["replacements"].append({"from": v, "to": target})
            added += 1

    _VOCAB.update(data)
    return added, skipped
