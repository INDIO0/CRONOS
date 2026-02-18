"""
Monitor Manager - Gerenciamento de Multiplos Monitores
======================================================
Detecta monitores conectados e move janelas para o segundo monitor quando disponivel.
"""

import os
import tkinter as tk
from typing import Optional, Tuple, List
import ctypes
from ctypes import wintypes


class MonitorInfo:
    """Informacoes sobre um monitor"""

    def __init__(self, index: int, x: int, y: int, width: int, height: int, is_primary: bool = False):
        self.index = index
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.is_primary = is_primary

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    def __repr__(self) -> str:
        primary = " (Primario)" if self.is_primary else ""
        return f"Monitor {self.index}{primary}: {self.width}x{self.height} at ({self.x}, {self.y})"


class MonitorManager:
    """Gerenciador de monitores do sistema"""

    def __init__(self):
        self.monitors: List[MonitorInfo] = []
        self._detect_monitors()

    def _detect_monitors(self):
        """Detecta todos os monitores conectados"""
        try:
            if self._detect_monitors_windows():
                return
            self._detect_monitors_tkinter()
        except Exception as e:
            print(f"Aviso: erro ao detectar monitores: {e}")
            self._detect_monitors_tkinter()

    def _detect_monitors_windows(self) -> bool:
        """Detecta monitores via WinAPI (com primario correto)."""
        try:
            user32 = ctypes.windll.user32

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            monitors: List[MonitorInfo] = []

            def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))
                rect = info.rcMonitor
                is_primary = bool(info.dwFlags & 1)
                monitors.append(
                    MonitorInfo(
                        index=len(monitors),
                        x=rect.left,
                        y=rect.top,
                        width=rect.right - rect.left,
                        height=rect.bottom - rect.top,
                        is_primary=is_primary
                    )
                )
                return 1

            MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
            user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_callback), 0)

            if monitors:
                if not any(m.is_primary for m in monitors):
                    monitors[0].is_primary = True
                self.monitors = monitors
                return True
        except Exception:
            return False
        return False

    def _detect_monitors_tkinter(self):
        """Detecta monitores usando tkinter (fallback)."""
        try:
            root = tk.Tk()
            root.withdraw()
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()

            primary_monitor = MonitorInfo(
                index=0,
                x=0,
                y=0,
                width=screen_width,
                height=screen_height,
                is_primary=True
            )
            self.monitors = [primary_monitor]

            try:
                test_window = tk.Toplevel(root)
                test_window.geometry(f"1x1+{screen_width + 10}+0")
                test_window.update()

                if test_window.winfo_x() >= screen_width:
                    second_monitor = MonitorInfo(
                        index=1,
                        x=screen_width,
                        y=0,
                        width=test_window.winfo_screenwidth() - screen_width,
                        height=screen_height,
                        is_primary=False
                    )
                    self.monitors.append(second_monitor)
                test_window.destroy()
            except Exception:
                pass

            root.destroy()
        except Exception:
            self.monitors = [MonitorInfo(0, 0, 0, 1920, 1080, True)]

    def get_monitor_count(self) -> int:
        return len(self.monitors)

    def has_multiple_monitors(self) -> bool:
        return len(self.monitors) > 1

    def get_primary_monitor(self) -> Optional[MonitorInfo]:
        for monitor in self.monitors:
            if monitor.is_primary:
                return monitor
        return self.monitors[0] if self.monitors else None

    def get_secondary_monitor(self) -> Optional[MonitorInfo]:
        if len(self.monitors) > 1:
            for monitor in self.monitors:
                if not monitor.is_primary:
                    return monitor
            return self.monitors[1]
        return None

    def get_monitor_by_index(self, index: int) -> Optional[MonitorInfo]:
        if 0 <= index < len(self.monitors):
            return self.monitors[index]
        return None

    def print_monitor_info(self):
        print("\n" + "=" * 60)
        print(f"Monitores detectados: {len(self.monitors)}")
        print("=" * 60)
        for monitor in self.monitors:
            print(f"  {monitor}")
        print("=" * 60 + "\n")


def _move_window_generic(window, x: int, y: int, width: int, height: int) -> bool:
    try:
        if hasattr(window, "move") and hasattr(window, "resize"):
            window.resize(width, height)
            window.move(x, y)
            return True
        if hasattr(window, "geometry"):
            window.geometry(f"{width}x{height}+{x}+{y}")
            if hasattr(window, "update_idletasks"):
                window.update_idletasks()
            return True
    except Exception:
        return False
    return False


def move_window_to_monitor(window: tk.Tk, monitor: MonitorInfo, width: int = 900, height: int = 900):
    try:
        x = monitor.x + (monitor.width - width) // 2
        y = monitor.y + (monitor.height - height) // 2
        ok = _move_window_generic(window, x, y, width, height)
        print(f"Janela movida para Monitor {monitor.index} em ({x}, {y})")
        return ok
    except Exception as e:
        print(f"Erro ao mover janela: {e}")
        return False


def move_cmd_to_monitor(monitor: MonitorInfo):
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return False

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        x = monitor.x + (monitor.width - width) // 2
        y = monitor.y + (monitor.height - height) // 2

        user32.SetWindowPos(hwnd, 0, int(x), int(y), width, height, 0x0040)
        print(f"CMD movido para Monitor {monitor.index}")
        return True
    except Exception as e:
        print(f"Erro ao mover CMD: {e}")
        return False


def move_window_to_primary(window: tk.Tk, width: int = 900, height: int = 900) -> bool:
    manager = MonitorManager()
    primary = manager.get_primary_monitor()
    if not primary:
        return False
    return move_window_to_monitor(window, primary, width, height)


def move_cmd_to_primary() -> bool:
    manager = MonitorManager()
    primary = manager.get_primary_monitor()
    if not primary:
        return False
    return move_cmd_to_monitor(primary)


def setup_secondary_monitor_mode(window: tk.Tk, width: int = 900, height: int = 900) -> bool:
    if os.getenv("CRONO_DISABLE_MONITOR_SETUP", "").strip().lower() in {"1", "true", "yes", "y"}:
        print("Monitor setup desativado por CRONO_DISABLE_MONITOR_SETUP.")
        return False
    monitor_manager = MonitorManager()
    monitor_manager.print_monitor_info()

    if monitor_manager.has_multiple_monitors():
        secondary_monitor = monitor_manager.get_secondary_monitor()
        primary_monitor = monitor_manager.get_primary_monitor()
        if secondary_monitor:
            print(f"Configurando Crono para operar no Monitor {secondary_monitor.index}...")
            move_window_to_monitor(window, secondary_monitor, width, height)
            move_cmd_to_monitor(secondary_monitor)
            print(f"Primario: {primary_monitor} | Secundario: {secondary_monitor}")
            return True

    print("Operando no monitor primario (segundo monitor nao detectado)")
    return False


def get_monitor_manager() -> MonitorManager:
    return MonitorManager()
