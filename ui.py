import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


class UILogStream:
    def __init__(self, ui, stream=None):
        self.ui = ui
        self.stream = stream
        self._buffer = ""

    def write(self, text):
        if not text:
            return
        self._buffer += str(text)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                try:
                    self.ui.add_log(line)
                except Exception:
                    pass
        if self.stream:
            try:
                self.stream.write(text)
            except Exception:
                pass

    def flush(self):
        if self._buffer:
            try:
                self.ui.add_log(self._buffer)
            except Exception:
                pass
            self._buffer = ""
        if self.stream:
            try:
                self.stream.flush()
            except Exception:
                pass

    def isatty(self):
        return False


class CronoUI:
    def __init__(self, size=(1280, 720)):
        self.size = size
        self._logs = []
        self._max_logs = 300
        self._redirect_active = False
        self._log_id = 0
        self._server = None
        self._server_thread = None
        self._port = int(os.getenv("CRONO_UI_PORT", "8765"))

        self._knowledge_submit_cb = None
        self._message_submit_cb = None
        self._memory_clear_short_cb = None
        self._memory_clear_long_cb = None
        self._memory_clear_visual_cb = None
        self._memory_refresh_cb = None

        self._on_standby_toggle = None
        self._on_snooze_toggle = None
        self._on_monitor_toggle = None
        self._on_proactive_vision_toggle = None
        self._on_ptt_toggle = None
        self._on_ptt_key_update = None

        self._controls_state = {
            "standby": False,
            "snooze": False,
            "monitor": False,
            "proactive_vision": False,
            "ptt": False,
        }
        self._settings_state = {
            "ptt_key": "insert",
        }

        self._memory_stats = {
            "short_count": 0,
            "long_count": 0,
            "has_last_screen": False,
            "has_last_image": False,
        }

        self._system_stats = {
            "cpu": 0.0,
            "ram": 0.0,
            "disk": 0.0,
            "gpu": None,
            "proc_ram_mb": None,
            "proc_ram_pct": None,
        }

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self._html_path = os.path.join(base_dir, "cronos_ui.html")
        # Compat: antigo código espera ui.root com geometry/update_idletasks
        self.root = self

    def _make_handler(self):
        ui = self

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, data: dict, code: int = 200):
                payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _send_file(self, path: str):
                try:
                    with open(path, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    if path.endswith(".html"):
                        ctype = "text/html; charset=utf-8"
                    elif path.endswith(".css"):
                        ctype = "text/css"
                    elif path.endswith(".js"):
                        ctype = "application/javascript"
                    else:
                        ctype = "application/octet-stream"
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                except Exception:
                    self.send_response(404)
                    self.end_headers()

            def do_GET(self):
                if self.path == "/" or self.path.startswith("/index"):
                    return self._send_file(ui._html_path)
                if self.path.startswith("/api/state"):
                    try:
                        last_id = 0
                        parsed = urlparse(self.path)
                        q = parse_qs(parsed.query or "")
                        since_vals = q.get("since") or []
                        if since_vals:
                            last_id = int(since_vals[0])
                        logs = [l for l in ui._logs if l["id"] > last_id]
                        return self._send_json(
                            {
                                "logs": logs,
                                "memory": ui._memory_stats,
                                "system": ui._system_stats,
                                "controls": ui._controls_state,
                                "settings": ui._settings_state,
                            }
                        )
                    except Exception:
                        return self._send_json(
                            {
                                "logs": [],
                                "memory": ui._memory_stats,
                                "system": ui._system_stats,
                                "controls": ui._controls_state,
                                "settings": ui._settings_state,
                            }
                        )
                return self._send_file(ui._html_path)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                try:
                    payload = json.loads(body)
                except Exception:
                    payload = {}

                if self.path == "/api/submit_knowledge":
                    text = payload.get("text", "")
                    if callable(ui._knowledge_submit_cb):
                        ui._knowledge_submit_cb(text)
                    return self._send_json({"ok": True})

                if self.path == "/api/submit_message":
                    text = payload.get("text", "")
                    if callable(ui._message_submit_cb):
                        ui._message_submit_cb(text)
                    return self._send_json({"ok": True})

                if self.path == "/api/clear_short":
                    if callable(ui._memory_clear_short_cb):
                        ui._memory_clear_short_cb()
                    return self._send_json({"ok": True})

                if self.path == "/api/clear_long":
                    if callable(ui._memory_clear_long_cb):
                        ui._memory_clear_long_cb()
                    return self._send_json({"ok": True})

                if self.path == "/api/clear_visual":
                    if callable(ui._memory_clear_visual_cb):
                        ui._memory_clear_visual_cb()
                    return self._send_json({"ok": True})

                if self.path == "/api/memory_stats":
                    if callable(ui._memory_refresh_cb):
                        ui._memory_refresh_cb()
                    return self._send_json(ui._memory_stats)

                if self.path == "/api/standby":
                    enabled = bool(payload.get("enabled"))
                    if callable(ui._on_standby_toggle):
                        ui._on_standby_toggle(enabled)
                    return self._send_json({"ok": True})

                if self.path == "/api/snooze":
                    enabled = bool(payload.get("enabled"))
                    if callable(ui._on_snooze_toggle):
                        ui._on_snooze_toggle(enabled)
                    return self._send_json({"ok": True})

                if self.path == "/api/monitor":
                    enabled = bool(payload.get("enabled"))
                    if callable(ui._on_monitor_toggle):
                        ui._on_monitor_toggle(enabled)
                    return self._send_json({"ok": True})

                if self.path == "/api/proactive_vision":
                    enabled = bool(payload.get("enabled"))
                    if callable(ui._on_proactive_vision_toggle):
                        ui._on_proactive_vision_toggle(enabled)
                    return self._send_json({"ok": True})

                if self.path == "/api/ptt":
                    enabled = bool(payload.get("enabled"))
                    if callable(ui._on_ptt_toggle):
                        ui._on_ptt_toggle(enabled)
                    return self._send_json({"ok": True})

                if self.path == "/api/ptt_key":
                    key = str(payload.get("key", "")).strip()
                    if callable(ui._on_ptt_key_update):
                        ui._on_ptt_key_update(key)
                    return self._send_json({"ok": True, "key": key})

                return self._send_json({"ok": False}, code=404)

            def log_message(self, *_args, **_kwargs):
                return

        return Handler

    def _start_server(self):
        handler = self._make_handler()
        self._server = ThreadingHTTPServer(("127.0.0.1", self._port), handler)
        self._server.serve_forever()

    def start(self):
        if not self._server_thread:
            self._server_thread = threading.Thread(target=self._start_server, daemon=True)
            self._server_thread.start()
            time.sleep(0.4)
            webbrowser.open(f"http://127.0.0.1:{self._port}/")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

    # Compat no-ops para monitor_manager
    def geometry(self, *_args, **_kwargs):
        return

    def update_idletasks(self):
        return

    def resize(self, *_args, **_kwargs):
        return True

    def move(self, *_args, **_kwargs):
        return True

    def attach_stdout_stderr(self):
        import sys
        self._redirect_active = True
        sys.stdout = UILogStream(self, stream=sys.__stdout__)
        sys.stderr = UILogStream(self, stream=sys.__stderr__)

    def write_log(self, text: str):
        self.add_log(text)

    def add_log(self, text: str):
        self._log_id += 1
        entry = {"id": self._log_id, "text": str(text)}
        self._logs.append(entry)
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

    def show_popup(self, title: str, body: str, duration_seconds: int = 12):
        self.add_log(f"[POPUP] {title}: {body}")

    def clear_popups(self):
        return

    def add_timer(self, title: str, duration_seconds: int):
        return

    def set_system_stats(self, cpu: float, ram: float, disk: float, gpu: float | None = None,
                         proc_ram_mb: float | None = None, proc_ram_pct: float | None = None):
        try:
            self._system_stats["cpu"] = float(cpu)
            self._system_stats["ram"] = float(ram)
            self._system_stats["disk"] = float(disk)
            self._system_stats["gpu"] = None if gpu is None else float(gpu)
            self._system_stats["proc_ram_mb"] = None if proc_ram_mb is None else float(proc_ram_mb)
            self._system_stats["proc_ram_pct"] = None if proc_ram_pct is None else float(proc_ram_pct)
        except Exception:
            pass

    def set_mic_level(self, level: float):
        return

    def start_speaking(self):
        return

    def stop_speaking(self):
        return

    def set_knowledge_submit_callback(self, callback: Callable[[str], Any]):
        self._knowledge_submit_cb = callback

    def set_message_submit_callback(self, callback: Callable[[str], Any]):
        self._message_submit_cb = callback

    def set_memory_panel_callbacks(self, clear_short=None, clear_long=None, clear_visual=None, refresh=None):
        self._memory_clear_short_cb = clear_short
        self._memory_clear_long_cb = clear_long
        self._memory_clear_visual_cb = clear_visual
        self._memory_refresh_cb = refresh

    def set_proactive_vision_callback(self, cb):
        self._on_proactive_vision_toggle = cb

    def set_ptt_callback(self, cb):
        self._on_ptt_toggle = cb

    def set_ptt_key_callback(self, cb):
        self._on_ptt_key_update = cb

    def update_memory_stats(self, stats: dict):
        if not isinstance(stats, dict):
            return
        for k in self._memory_stats.keys():
            if k in stats:
                self._memory_stats[k] = stats.get(k)

    def set_standby_callback(self, callback: Callable[[bool], Any]):
        self._on_standby_toggle = callback

    def set_snooze_callback(self, callback: Callable[[bool], Any]):
        self._on_snooze_toggle = callback

    def set_monitor_toggle_callback(self, callback: Callable[[bool], Any]):
        self._on_monitor_toggle = callback

    def set_standby_state(self, enabled: bool):
        self._controls_state["standby"] = bool(enabled)
        return

    def set_snooze_state(self, enabled: bool):
        self._controls_state["snooze"] = bool(enabled)
        return

    def set_monitor_state(self, enabled: bool):
        self._controls_state["monitor"] = bool(enabled)
        return

    def set_proactive_vision_state(self, enabled: bool):
        self._controls_state["proactive_vision"] = bool(enabled)
        return

    def set_ptt_state(self, enabled: bool):
        self._controls_state["ptt"] = bool(enabled)
        return

    def set_ptt_key(self, key: str):
        clean = str(key or "").strip().lower()
        self._settings_state["ptt_key"] = clean or "insert"
        return

    def maximize(self):
        return
