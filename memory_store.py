import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class MemoryStore:
    """
    New memory system for Crono.
    - Short-term: last N messages (JSON)
    - Long-term: remembered notes/profile/project memories (JSON)
    - Visual: last screen/image description (JSON)
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        short_file: str = "memory_short.json",
        long_file: str = "memory_long.json",
        visual_file: str = "memory_visual.json",
        short_limit: int = 20,
    ):
        base_dir = base_dir or os.getcwd()
        self._base_dir = base_dir
        self.short_path = os.path.join(base_dir, short_file)
        self.long_path = os.path.join(base_dir, long_file)
        self.visual_path = os.path.join(base_dir, visual_file)
        self.short_limit = short_limit
        self._lock = threading.Lock()
        self._short: List[Dict[str, Any]] = []
        self._long_entries: List[Dict[str, Any]] = []
        self._profile: Dict[str, Any] = {}
        self._visual: Dict[str, Any] = {
            "last_screen": None,
            "last_image": None,
            "last_opened_website": None,
        }
        self._load()
        self._maybe_migrate_legacy()

    def _load(self) -> None:
        self._short = self._read_json(self.short_path, default=[])
        long_data = self._read_json(self.long_path, default={"entries": [], "profile": {}})
        if isinstance(long_data, dict):
            self._long_entries = long_data.get("entries") or []
            self._profile = long_data.get("profile") or {}
        else:
            self._long_entries = []
            self._profile = {}
        self._visual = self._read_json(
            self.visual_path,
            default={"last_screen": None, "last_image": None, "last_opened_website": None},
        )
        if not isinstance(self._short, list):
            self._short = []
        if not isinstance(self._long_entries, list):
            self._long_entries = []
        if not isinstance(self._profile, dict):
            self._profile = {}
        if not isinstance(self._visual, dict):
            self._visual = {"last_screen": None, "last_image": None, "last_opened_website": None}

    def _maybe_migrate_legacy(self) -> None:
        legacy_path = os.path.join(self._base_dir, "memory.json")
        if not os.path.exists(legacy_path):
            return
        # Only migrate if new stores are empty
        if self._short or self._long_entries or self._profile or any(self._visual.values()):
            return
        legacy = self._read_json(legacy_path, default={})
        if not isinstance(legacy, dict):
            return
        # Migrate profile
        profile = legacy.get("profile")
        if isinstance(profile, dict):
            self._profile = profile
        # Migrate notes to long-term entries
        notes = legacy.get("notes")
        if isinstance(notes, list):
            for n in notes:
                note_text = n.get("note") if isinstance(n, dict) else None
                ts = n.get("ts") if isinstance(n, dict) else None
                if note_text:
                    self._long_entries.append(
                        {
                            "id": str(uuid.uuid4()),
                            "ts": float(ts) if ts else time.time(),
                            "kind": "note",
                            "content": str(note_text),
                            "tags": "migrado",
                            "source": "legacy",
                            "context": "",
                        }
                    )
        # Migrate messages to short-term (last N)
        msgs = legacy.get("messages")
        if isinstance(msgs, list):
            for m in msgs[-self.short_limit :]:
                if not isinstance(m, dict):
                    continue
                role = m.get("role") or "user"
                content = m.get("content") or ""
                ts = m.get("ts")
                if content:
                    self._short.append(
                        {
                            "ts": float(ts) if ts else time.time(),
                            "role": role,
                            "content": content,
                        }
                    )
        # Migrate visual context
        last_screen = legacy.get("last_screen")
        if isinstance(last_screen, dict):
            self._visual["last_screen"] = last_screen
        last_image = legacy.get("last_image")
        if isinstance(last_image, dict):
            self._visual["last_image"] = last_image
        last_site = legacy.get("last_opened_website")
        if isinstance(last_site, dict):
            self._visual["last_opened_website"] = last_site

        self._save_short()
        self._save_long()
        self._save_visual()

    def _read_json(self, path: str, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json(self, path: str, data) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            return

    def _save_short(self) -> None:
        self._write_json(self.short_path, self._short)

    def _save_long(self) -> None:
        self._write_json(self.long_path, {"entries": self._long_entries, "profile": self._profile})

    def _save_visual(self) -> None:
        self._write_json(self.visual_path, self._visual)

    def start_session(self, *args, **kwargs) -> str:
        return str(uuid.uuid4())

    def add_message(self, role: str, content: str) -> None:
        if not content:
            return
        with self._lock:
            self._short.append(
                {
                    "ts": time.time(),
                    "role": role or "user",
                    "content": content,
                }
            )
            if len(self._short) > self.short_limit:
                self._short = self._short[-self.short_limit :]
            self._save_short()

    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._short[-max(1, limit) :])

    def add_long_term(
        self,
        content: str,
        kind: str = "note",
        tags: str | list[str] = "",
        source: str = "voice",
        context: str = "",
    ) -> None:
        content = str(content or "").strip()
        if not content:
            return
        tags_text = self._normalize_tags(tags)
        with self._lock:
            self._long_entries.append(
                {
                    "id": str(uuid.uuid4()),
                    "ts": time.time(),
                    "kind": kind,
                    "content": content,
                    "tags": tags_text,
                    "source": source,
                    "context": context,
                }
            )
            if len(self._long_entries) > 5000:
                self._long_entries = self._long_entries[-5000:]
            self._save_long()

    def search_long_term(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.search_long_term_scoped(query=query, limit=limit)

    def search_long_term_scoped(
        self,
        query: str,
        limit: int = 5,
        project: str | None = None,
        person: str | None = None,
    ) -> List[Dict[str, Any]]:
        query = str(query or "").strip().lower()
        if not query:
            return []
        project_tag = f"project:{self._slug(project)}" if project else None
        person_tag = f"person:{self._slug(person)}" if person else None
        date_range = self._infer_date_range(query)
        hits = []
        with self._lock:
            for item in reversed(self._long_entries):
                text = str(item.get("content", "")).lower()
                tags = str(item.get("tags", "")).lower()
                if project_tag and project_tag not in tags:
                    continue
                if person_tag and person_tag not in tags:
                    continue
                if query in text or query in tags:
                    if date_range and not self._in_range(item.get("ts"), date_range):
                        continue
                    hits.append(item)
                if len(hits) >= limit:
                    break
        return list(reversed(hits))

    def get_last_long_term(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._long_entries[-max(1, limit) :])

    # Compatibility profile helpers
    def get_profile(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._profile)

    def set_profile_field(self, key: str, value: Any) -> None:
        if not key or value in (None, ""):
            return
        with self._lock:
            self._profile[key] = value
            self._save_long()

    def update_profile_from_memory_update(self, memory_update: Dict[str, Any]) -> None:
        if not isinstance(memory_update, dict) or not memory_update:
            return
        with self._lock:
            for key, value in memory_update.items():
                if value not in (None, ""):
                    self._profile[key] = value
            self._save_long()

    # Compatibility note helpers (maps to long-term)
    def search_notes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        hits = self.search_long_term(query, limit=limit)
        normalized = []
        for h in hits:
            item = dict(h)
            if "note" not in item and item.get("content"):
                item["note"] = item.get("content")
            normalized.append(item)
        return normalized

    def get_recent_notes(self, limit: int = 5) -> List[Dict[str, Any]]:
        hits = self.get_last_long_term(limit=limit)
        normalized = []
        for h in hits:
            item = dict(h)
            if "note" not in item and item.get("content"):
                item["note"] = item.get("content")
            normalized.append(item)
        return normalized

    def add_remember_note(self, note: str, source: str = "voice") -> None:
        self.add_long_term(note, kind="note", source=source)

    def add_scoped_note(
        self,
        note: str,
        source: str = "voice",
        project: str | None = None,
        person: str | None = None,
    ) -> None:
        tags: list[str] = []
        if project:
            tags.append(f"project:{self._slug(project)}")
        if person:
            tags.append(f"person:{self._slug(person)}")
        self.add_long_term(note, kind="note", source=source, tags=tags)

    def add_preference(self, value: str) -> None:
        value = str(value or "").strip()
        if not value:
            return
        with self._lock:
            prefs = self._profile.get("preferences") or []
            if value not in prefs:
                prefs.append(value)
            self._profile["preferences"] = prefs
            self._save_long()

    def format_recent_summaries(self, limit: int = 4) -> str:
        return ""

    def get_active_context(self):
        return None, None

    def set_last_screen(self, description: str, source: str = "vision") -> None:
        description = str(description or "").strip()
        if not description:
            return
        with self._lock:
            self._visual["last_screen"] = {
                "ts": time.time(),
                "description": description,
                "source": source,
            }
            self._save_visual()

    def get_last_screen(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._visual.get("last_screen")

    def set_last_image(self, description: str, source: str = "vision") -> None:
        description = str(description or "").strip()
        if not description:
            return
        with self._lock:
            self._visual["last_image"] = {
                "ts": time.time(),
                "description": description,
                "source": source,
            }
            self._save_visual()

    def get_last_image(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._visual.get("last_image")

    def set_last_opened_website(self, url: str) -> None:
        url = str(url or "").strip()
        if not url:
            return
        with self._lock:
            self._visual["last_opened_website"] = {
                "ts": time.time(),
                "url": url,
            }
            self._save_visual()

    def get_last_opened_website(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._visual.get("last_opened_website")

    def clear_short_term(self) -> None:
        with self._lock:
            self._short = []
            self._save_short()

    def clear_long_term(self) -> None:
        with self._lock:
            self._long_entries = []
            self._profile = {}
            self._save_long()

    def clear_visual(self) -> None:
        with self._lock:
            self._visual = {"last_screen": None, "last_image": None, "last_opened_website": None}
            self._save_visual()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "short_count": len(self._short),
                "long_count": len(self._long_entries),
                "has_last_screen": bool(self._visual.get("last_screen")),
                "has_last_image": bool(self._visual.get("last_image")),
            }

    def _infer_date_range(self, query: str) -> Optional[Tuple[float, float]]:
        now = datetime.now()
        q = query.lower()
        if "hoje" in q:
            start = datetime(now.year, now.month, now.day)
            end = start + timedelta(days=1)
            return start.timestamp(), end.timestamp()
        if "ontem" in q:
            start = datetime(now.year, now.month, now.day) - timedelta(days=1)
            end = start + timedelta(days=1)
            return start.timestamp(), end.timestamp()
        if "anteontem" in q or "antes de ontem" in q:
            start = datetime(now.year, now.month, now.day) - timedelta(days=2)
            end = start + timedelta(days=1)
            return start.timestamp(), end.timestamp()
        if "semana passada" in q:
            start = datetime(now.year, now.month, now.day) - timedelta(days=7)
            end = datetime(now.year, now.month, now.day)
            return start.timestamp(), end.timestamp()
        if "mes passado" in q or "mês passado" in q:
            start = datetime(now.year, now.month, 1) - timedelta(days=1)
            start = datetime(start.year, start.month, 1)
            end = datetime(now.year, now.month, 1)
            return start.timestamp(), end.timestamp()
        return None

    def _in_range(self, ts: Any, date_range: Tuple[float, float]) -> bool:
        try:
            ts_val = float(ts)
        except Exception:
            return False
        start, end = date_range
        return start <= ts_val < end

    def _normalize_tags(self, tags: str | list[str]) -> str:
        if isinstance(tags, list):
            clean = [str(t).strip().lower() for t in tags if str(t).strip()]
            return ",".join(clean)
        return str(tags or "").strip().lower()

    def _slug(self, value: str | None) -> str:
        if not value:
            return ""
        text = str(value).strip().lower()
        text = "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else " " for ch in text)
        text = "_".join(text.split())
        return text


def get_memory_store() -> MemoryStore:
    return MemoryStore()
