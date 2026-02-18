import json
import datetime
import urllib.request
from zoneinfo import ZoneInfo


def build_startup_greeting() -> str:
    """
    Build a startup greeting with local time and Sao Paulo weather.
    Returns a single spoken sentence.
    """
    now = _now_sp()
    greeting = _time_greeting(now.hour)
    time_text = _format_time_12h(now)
    period = _period_label(now.hour)

    weather = _fetch_sp_weather()
    if weather:
        temp = weather.get("temp_c")
        desc = weather.get("desc")
        tmax = weather.get("tmax_c")
        tmin = weather.get("tmin_c")
        precip = weather.get("precip_pct")

        parts = [
            f"{greeting}, senhor. Agora sao {time_text} {period}.",
            f"O clima para Sao Paulo e de {temp} graus, {desc}."
        ]

        forecast = []
        if tmax is not None:
            forecast.append(f"maxima de {tmax} graus")
        if tmin is not None:
            forecast.append(f"minima de {tmin} graus")
        if precip is not None:
            forecast.append(f"chance de chuva de {precip} por cento")

        if forecast:
            parts.append("A previsao de hoje e " + ", ".join(forecast) + ".")

        return " ".join(parts)

    return (
        f"{greeting}, senhor. Agora sao {time_text} {period}. "
        "No momento nao consegui consultar o clima para Sao Paulo."
    )


def _now_sp() -> datetime.datetime:
    try:
        return datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        return datetime.datetime.now()


def _format_time_12h(dt: datetime.datetime) -> str:
    hour = dt.hour % 12
    if hour == 0:
        hour = 12
    return f"{hour}:{dt.strftime('%M')}"


def _time_greeting(hour: int) -> str:
    if 5 <= hour < 12:
        return "bom dia"
    if 12 <= hour < 18:
        return "boa tarde"
    if 18 <= hour < 24:
        return "boa noite"
    return "boa madrugada"


def _period_label(hour: int) -> str:
    if 5 <= hour < 12:
        return "da manha"
    if 12 <= hour < 18:
        return "da tarde"
    if 18 <= hour < 24:
        return "da noite"
    return "da madrugada"


def _fetch_sp_weather() -> dict | None:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=-23.55&longitude=-46.63"
        "&current=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        "&timezone=America%2FSao_Paulo"
    )

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
    except Exception:
        return None

    try:
        current = data.get("current", {}) or {}
        daily = data.get("daily", {}) or {}

        temp = _round_int(current.get("temperature_2m"))
        code = current.get("weather_code")
        desc = _weather_desc(code)

        tmax = _first_daily(daily.get("temperature_2m_max"))
        tmin = _first_daily(daily.get("temperature_2m_min"))
        precip = _first_daily(daily.get("precipitation_probability_max"))

        return {
            "temp_c": temp,
            "desc": desc,
            "tmax_c": _round_int(tmax),
            "tmin_c": _round_int(tmin),
            "precip_pct": _round_int(precip),
        }
    except Exception:
        return None


def _first_daily(values):
    if isinstance(values, list) and values:
        return values[0]
    return None


def _round_int(value):
    try:
        return int(round(float(value)))
    except Exception:
        return None


def _weather_desc(code) -> str:
    mapping = {
        0: "ceu limpo",
        1: "principalmente limpo",
        2: "parcialmente nublado",
        3: "nublado",
        45: "nevoeiro",
        48: "nevoeiro",
        51: "garoa leve",
        53: "garoa",
        55: "garoa forte",
        56: "garoa gelada leve",
        57: "garoa gelada forte",
        61: "chuva fraca",
        63: "chuva",
        65: "chuva forte",
        66: "chuva congelante leve",
        67: "chuva congelante forte",
        71: "neve fraca",
        73: "neve",
        75: "neve forte",
        77: "grao de neve",
        80: "pancadas fracas",
        81: "pancadas",
        82: "pancadas fortes",
        85: "neve fraca",
        86: "neve forte",
        95: "trovoadas",
        96: "trovoadas com granizo",
        99: "trovoadas com granizo forte",
    }
    return mapping.get(code, "condicoes indefinidas")
