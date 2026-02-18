import os
import uuid
from datetime import datetime, timedelta

from tts import edge_speak


def _safe_log(player, text: str):
    if not text:
        return
    if player:
        try:
            player.write_log(text)
        except Exception:
            pass


def _escape_ics_text(text: str) -> str:
    if text is None:
        return ""
    t = str(text)
    t = t.replace("\\", "\\\\")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\n", "\\n")
    t = t.replace(";", "\\;").replace(",", "\\,")
    return t


def _parse_dt(value: str) -> tuple[datetime | None, bool]:
    if not value:
        return None, False
    v = str(value).strip()
    if not v:
        return None, False

    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        try:
            dt = datetime.fromisoformat(v)
            return dt, True
        except Exception:
            pass

    if v.endswith("Z"):
        v = v[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt, False
    except Exception:
        return None, False


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _build_rrule(params: dict) -> str | None:
    recurrence = params.get("recurrence") if isinstance(params.get("recurrence"), dict) else {}
    freq = params.get("recurrence_freq") or params.get("freq") or recurrence.get("freq")
    if not freq:
        return None
    freq = str(freq).strip().upper()
    if freq not in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}:
        return None

    parts = [f"FREQ={freq}"]
    interval = params.get("recurrence_interval") or recurrence.get("interval")
    count = params.get("recurrence_count") or recurrence.get("count")
    until = params.get("recurrence_until") or recurrence.get("until")
    byday = params.get("recurrence_byday") or recurrence.get("byday")

    try:
        if interval is not None and int(interval) > 1:
            parts.append(f"INTERVAL={int(interval)}")
    except Exception:
        pass
    try:
        if count is not None and int(count) > 0:
            parts.append(f"COUNT={int(count)}")
    except Exception:
        pass

    if until:
        dt, is_all_day = _parse_dt(str(until))
        if dt:
            if is_all_day:
                parts.append(f"UNTIL={dt.strftime('%Y%m%d')}")
            else:
                parts.append(f"UNTIL={dt.strftime('%Y%m%dT235959')}")

    if byday:
        if isinstance(byday, str):
            days = [d.strip().upper() for d in byday.replace(";", ",").split(",") if d.strip()]
        elif isinstance(byday, list):
            days = [str(d).strip().upper() for d in byday if str(d).strip()]
        else:
            days = []
        valid_days = [d for d in days if d in {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}]
        if valid_days:
            parts.append("BYDAY=" + ",".join(valid_days))

    return ";".join(parts)


def _parse_reminders(params: dict) -> list[int]:
    reminders = []
    base = params.get("reminder_minutes") or params.get("reminder_min")
    if base is not None:
        try:
            val = int(base)
            if val > 0:
                reminders.append(val)
        except Exception:
            pass

    snooze = params.get("snooze_minutes")
    if isinstance(snooze, list):
        for x in snooze:
            try:
                v = int(x)
                if v > 0:
                    reminders.append(v)
            except Exception:
                pass
    elif snooze is not None:
        try:
            v = int(snooze)
            if v > 0:
                reminders.append(v)
        except Exception:
            pass

    # unique + sorted descending (longer first)
    return sorted(set(reminders), reverse=True)


def schedule_calendar_action(
    parameters: dict,
    response: str | None = None,
    player=None,
    session_memory=None,
) -> bool:
    """
    Schedule a calendar entry by generating an .ics file and opening it.
    Supports recurrence and multiple reminders.
    """
    params = parameters or {}

    title = (params.get("title") or params.get("summary") or params.get("task") or params.get("name") or "").strip()
    start_raw = params.get("start") or params.get("start_datetime") or params.get("datetime") or ""
    end_raw = params.get("end") or params.get("end_datetime") or ""

    if not title:
        title = "Tarefa agendada"

    start_dt, parsed_all_day = _parse_dt(start_raw)
    all_day = bool(params.get("all_day")) or bool(parsed_all_day)

    if start_dt is None:
        msg = "Qual o dia e a hora para agendar no calendario? Exemplo: 2026-02-06 14:00."
        _safe_log(player, f"Crono: {msg}")
        edge_speak(msg, player)
        return False

    end_dt = None
    if end_raw:
        end_dt, _ = _parse_dt(end_raw)

    duration_minutes = params.get("duration_minutes") or params.get("duration_min") or params.get("duration") or 30
    try:
        duration_minutes = int(duration_minutes)
    except Exception:
        duration_minutes = 30
    if duration_minutes <= 0:
        duration_minutes = 30

    if end_dt is None:
        if all_day:
            end_dt = start_dt + timedelta(days=1)
        else:
            end_dt = start_dt + timedelta(minutes=duration_minutes)

    description = (params.get("description") or params.get("notes") or "").strip()
    location = (params.get("location") or "").strip()
    reminders = _parse_reminders(params)
    rrule = _build_rrule(params)

    uid = str(uuid.uuid4())
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CRONO//Calendar//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
    ]

    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{start_dt.strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{end_dt.strftime('%Y%m%d')}")
    else:
        lines.append(f"DTSTART:{_fmt_dt(start_dt)}")
        lines.append(f"DTEND:{_fmt_dt(end_dt)}")

    lines.append(f"SUMMARY:{_escape_ics_text(title)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape_ics_text(description)}")
    if location:
        lines.append(f"LOCATION:{_escape_ics_text(location)}")
    if rrule:
        lines.append(f"RRULE:{rrule}")

    for minutes in reminders:
        lines.extend(
            [
                "BEGIN:VALARM",
                f"TRIGGER:-PT{int(minutes)}M",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_escape_ics_text(title)}",
                "END:VALARM",
            ]
        )

    lines.extend(
        [
            "END:VEVENT",
            "END:VCALENDAR",
        ]
    )

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(base_dir, "calendar_events")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"crono_event_{uid}.ics"
    out_path = os.path.join(out_dir, filename)

    try:
        with open(out_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\r\n".join(lines) + "\r\n")
    except Exception as e:
        msg = "Nao consegui criar o arquivo do evento do calendario."
        _safe_log(player, f"Crono: {msg} ({e})")
        edge_speak(msg, player)
        return False

    speak_msg = response or "Certo. Vou abrir o evento no seu calendario para voce confirmar."
    _safe_log(player, f"Crono: {speak_msg} ({out_path})")
    edge_speak(speak_msg, player)

    try:
        os.startfile(out_path)
        return True
    except Exception as e:
        msg = f"Criei o evento, mas nao consegui abrir automaticamente. O arquivo esta em {out_path}."
        _safe_log(player, f"Crono: {msg} ({e})")
        edge_speak(msg, player)
        return False
