"""
Crono STS - Full-Duplex Voice Assistant
======================================
Main entry point for the Crono AI Assistant (Moshi-style STS).

Features:
- Full-duplex listening (hear you while speaking)
- Instant interruption (just start talking)
- Low latency streaming (~500ms)
- Echo cancellation (won't hear itself)
"""

import os
import sys
import threading
import asyncio
import traceback
from importlib.util import find_spec

# Ensure correct path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)


def check_dependencies() -> bool:
    """Verify required packages are installed without importing side effects."""
    required = {
        "python-dotenv": "dotenv",
        "requests": "requests",
        "sounddevice": "sounddevice",
        "soundfile": "soundfile",
        "numpy": "numpy",
        "edge-tts": "edge_tts",
        "groq": "groq",
        "psutil": "psutil",
        "pyautogui": "pyautogui",
        "Pillow": "PIL",
        "keyboard": "keyboard",
        "pyperclip": "pyperclip",
        "imageio": "imageio",
        "imageio-ffmpeg": "imageio_ffmpeg",
    }
    optional = {
        # Add optional imports here if you decide to make features non-blocking
    }

    missing_required = []
    missing_optional = []

    for pip_name, import_name in required.items():
        if find_spec(import_name) is None:
            missing_required.append(pip_name)

    for pip_name, import_name in optional.items():
        if find_spec(import_name) is None:
            missing_optional.append(pip_name)

    if missing_required or missing_optional:
        if missing_required:
            print("Missing required dependencies:")
            for pkg in missing_required:
                print(f"  - {pkg}")
            print("\nInstall with: pip install " + " ".join(missing_required))
        if missing_optional:
            print("\nOptional dependencies missing:")
            for pkg in missing_optional:
                print(f"  - {pkg}")
        return not missing_required

    return True


def main():
    """Launch Crono STS"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass
    if not check_dependencies():
        input("\nPressione Enter para sair...")
        return

    print(
        "\n"
        "============================================================\n"
        " Crono STS - Full-Duplex Voice Mode\n"
        "------------------------------------------------------------\n"
        " Fale naturalmente - estou sempre ouvindo\n"
        " Me interrompa quando quiser\n"
        " Cancelamento de eco ativo\n"
        "============================================================\n"
    )

    try:
        from ui import CronoUI
        from monitor_manager import setup_secondary_monitor_mode, move_window_to_primary, move_cmd_to_primary
        from sts_orchestrator import CronoSTSOrchestrator
        from llm import init_cerebro_runtime

        # Initialize UI
        ui = CronoUI(size=(720, 520))
        ui.attach_stdout_stderr()

        def _on_monitor_toggle(enabled: bool):
            if enabled:
                ok = setup_secondary_monitor_mode(ui.root, width=720, height=520)
                ui.set_monitor_state(ok)
            else:
                move_window_to_primary(ui.root, width=720, height=520)
                move_cmd_to_primary()

        ui.set_monitor_toggle_callback(_on_monitor_toggle)

        moved = setup_secondary_monitor_mode(ui.root, width=720, height=520)
        ui.set_monitor_state(moved)
        ui.maximize()
        # Inicializar cerebro e prompt em ordem
        init_cerebro_runtime()

        # Initialize and run Orchestrator
        orchestrator = CronoSTSOrchestrator(ui)

        def runner():
            asyncio.run(orchestrator.run())

        threading.Thread(target=runner, daemon=True).start()

        # Start UI loop
        ui.start()

    except Exception as e:
        print(f"Erro fatal ao iniciar: {e}")
        print(traceback.format_exc())
        input("Pressione Enter para sair...")


if __name__ == "__main__":
    main()
