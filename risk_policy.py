"""
Deterministic risk policy for Crono plan steps.
"""
from __future__ import annotations

from typing import Dict

from core.plan_schema import PlanStep


def assess_risk(step: PlanStep) -> str:
    """
    Return risk level: safe | sensitive | destructive
    """
    intent = step.intent
    params: Dict = step.parameters or {}

    if intent == "file_operation":
        action = str(params.get("action") or "").lower()
        if action.startswith("delete"):
            return "destructive"
        if action in {"edit_file"}:
            return "sensitive"
        if action in {"create_file", "create_folder"}:
            return "sensitive"
        if action in {"read_file", "list_files"}:
            return "safe"
        return "sensitive"

    if intent in {"control_screen", "visual_navigate"}:
        return "sensitive"

    if intent in {"press_key", "type_text"}:
        return "sensitive"

    if intent in {"open_app", "close_app", "open_website", "weather_report", "describe_screen", "play_media", "chat"}:
        return "safe"

    if intent in {"set_timer", "schedule_calendar"}:
        return "safe"

    if intent in {"create_directory", "scan_directory", "list_directory", "get_file_info"}:
        if intent == "create_directory":
            return "sensitive"
        return "safe"

    if intent == "project_manager":
        return "sensitive"

    if intent == "video_analysis":
        return "safe"

    if intent == "system_command":
        command = str(params.get("command") or params.get("cmd") or "").lower()
        destructive_markers = [
            "remove-item", "del ", "erase ", "rd ", "rmdir",
            "format", "clear-content", "cipher /w", "diskpart",
            "shutdown", "restart-computer", "stop-computer"
        ]
        if any(marker in command for marker in destructive_markers):
            return "destructive"
        return "sensitive"

    return "sensitive"


def requires_confirmation(risk_level: str) -> bool:
    """
    Lenient policy: confirm only destructive actions.
    """
    return risk_level in {"destructive"}
