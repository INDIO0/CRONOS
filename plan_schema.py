"""
Plan schema normalization and validation for Crono
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import uuid


RISK_LEVELS = {"safe", "sensitive", "destructive"}

# Intents supported by the orchestrator handlers
KNOWN_INTENTS = {
    "open_app",
    "close_app",
    "type_text",
    "press_key",
    "open_website",
    "weather_report",
    "file_operation",
    "project_manager",
    "describe_screen",
    "play_media",
    "visual_navigate",
    "control_screen",
    "video_analysis",
    "chat",
    "create_directory",
    "scan_directory",
    "list_directory",
    "get_file_info",
    "remember_note",
    "system_command",
    "set_timer",
    "cancel_timer",
    "schedule_calendar",
    "system_status",
    "clear_popups",
    "search_web",
    "fetch_web_content",
    "memory_durable_fact",
    "search_personal_data",
    "graphic_art",
    "load_skills",
    "multi_tool_use.parallel",
}

RISK_ALIASES = {
    "low": "safe",
    "safe": "safe",
    "normal": "sensitive",
    "medium": "sensitive",
    "moderate": "sensitive",
    "sensitive": "sensitive",
    "high": "sensitive",
    "dangerous": "destructive",
    "destructive": "destructive",
    "critical": "destructive",
}


@dataclass
class PlanStep:
    step_id: str
    intent: str
    parameters: Dict[str, Any]
    risk: str
    requires_confirmation: bool
    summary: str


@dataclass
class PlanEnvelope:
    plan_id: str
    goal: str
    needs_clarification: bool
    clarifying_question: Optional[str]
    plan: List[PlanStep]
    response: Optional[str]


def _uuid() -> str:
    return str(uuid.uuid4())


def normalize_plan(raw: Dict[str, Any]) -> PlanEnvelope:
    """
    Normalize raw LLM output into a PlanEnvelope.
    Does not enforce intent validity; validation is separate.
    """
    plan_id = str(raw.get("plan_id") or _uuid())
    goal = str(raw.get("goal") or "").strip()
    needs_clarification = bool(raw.get("needs_clarification", False))
    clarifying_question = raw.get("clarifying_question")
    response = raw.get("response")

    raw_plan = raw.get("plan") or []
    if not isinstance(raw_plan, list):
        raw_plan = []

    normalized_steps: List[PlanStep] = []
    for step in raw_plan:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or _uuid())
        intent = str(step.get("intent") or "").strip()
        parameters = step.get("parameters") or {}
        if not isinstance(parameters, dict):
            parameters = {}
        raw_risk = str(step.get("risk") or "safe").strip().lower()
        risk = RISK_ALIASES.get(raw_risk, "safe")
        requires_confirmation = bool(step.get("requires_confirmation", False))
        summary = str(step.get("summary") or "").strip()

        normalized_steps.append(
            PlanStep(
                step_id=step_id,
                intent=intent,
                parameters=parameters,
                risk=risk,
                requires_confirmation=requires_confirmation,
                summary=summary,
            )
        )

    return PlanEnvelope(
        plan_id=plan_id,
        goal=goal,
        needs_clarification=needs_clarification,
        clarifying_question=clarifying_question,
        plan=normalized_steps,
        response=response,
    )


def validate_plan(plan: PlanEnvelope) -> Tuple[bool, Optional[str]]:
    """
    Validate a PlanEnvelope structure and intents.
    """
    if not isinstance(plan.plan, list):
        return False, "Plan must be a list"

    for idx, step in enumerate(plan.plan):
        if not step.intent:
            return False, f"Missing intent at step {idx + 1}"
        if step.intent not in KNOWN_INTENTS:
            return False, f"Unknown intent '{step.intent}' at step {idx + 1}"
        if step.risk not in RISK_LEVELS:
            return False, f"Invalid risk '{step.risk}' at step {idx + 1}"

    return True, None
