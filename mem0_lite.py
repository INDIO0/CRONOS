import json
import os
import re
import threading
import time
from typing import List, Tuple


class Mem0Lite:
    """
    Lightweight memory store with simple extraction and keyword search.
    Stores items in a JSON file for persistence.
    """

    def __init__(self, base_dir: str | None = None, filename: str = "mem0.json"):
        base_dir = base_dir or os.getcwd()
        self.path = os.path.join(base_dir, filename)
        self._lock = threading.Lock()
        self._items = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._items = data
        except Exception:
            return

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._items, f, indent=2, ensure_ascii=False)
        except Exception:
            return

    def extract_memories(self, text: str) -> List[Tuple[str, str, str]]:
        """
        Extract (kind, content, tags) from user text.
        """
        if not text:
            return []
        t = text.strip()
        if not t:
            return []
        tl = t.lower()

        memories: List[Tuple[str, str, str]] = []

        # Basic preference
        m = re.search(r"\blembre que gosto de\b(.+)$", tl)
        if m:
            value = m.group(1).strip()
            if value:
                memories.append(("preference", value, "preferencia"))
                return memories

        # Remember note
        m = re.search(r"\b(lembre|lembra|memoriza|guarda|salva) (:que )(.+)$", tl)
        if m:
            value = m.group(2).strip()
            if value:
                memories.append(("note", value, "lembrete"))
                return memories

        # Name declaration
        m = re.search(r"\bmeu nome e\b(.+)$", tl)
        if m:
            value = m.group(1).strip()
            if value:
                memories.append(("profile", f"nome={value}", "nome"))

        return memories

    def add_memory(self, kind: str, content: str, source: str = "", tags: str = "") -> None:
        if not content:
            return
        with self._lock:
            self._items.append(
                {
                    "ts": time.time(),
                    "kind": kind,
                    "content": content,
                    "source": source,
                    "tags": tags,
                }
            )
            if len(self._items) > 1000:
                self._items = self._items[-1000:]
            self._save()

    def search(self, query: str, limit: int = 5) -> List[dict]:
        if not query:
            return []
        q = query.lower().strip()
        if not q:
            return []
        hits = []
        with self._lock:
            for item in reversed(self._items):
                content = str(item.get("content", "")).lower()
                if q in content:
                    hits.append(item)
                if len(hits) >= limit:
                    break
        return list(reversed(hits))
