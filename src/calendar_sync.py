import os
from datetime import datetime, timedelta, date
from typing import List, Tuple, Any, Dict

from dotenv import load_dotenv
import requests
import pytz
from icalendar import Calendar as ICal

load_dotenv()

TZ_NAME = os.getenv("TZ", "America/Mexico_City")
STUDY_BLOCK_MIN = int(os.getenv("STUDY_BLOCK_MINUTES", "60"))
ICAL_URL = os.getenv("GOOGLE_ICAL_URL", "")

# Ventana laboral para sugerir estudio
WORKDAY_START = 8    # 08:00
WORKDAY_END = 21     # 21:00


def _today_window(tzname: str) -> Tuple[datetime, datetime]:
    tz = pytz.timezone(tzname)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _to_local_dt(val: Any, tz: Any) -> datetime:
    """
    Convierte DTSTART/DTEND que pueden venir como date o datetime a datetime con TZ local.
    - Si es 'date' (evento de día completo), lo tratamos como 00:00 local.
    - Si es 'datetime' naive, lo localizamos; si trae tz, lo convertimos a tz local.
    """
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return tz.localize(val)
        return val.astimezone(tz)
    if isinstance(val, date):
        # Evento de día completo: medianoche local
        return tz.localize(datetime(val.year, val.month, val.day, 0, 0, 0))
    raise ValueError(f"No se pudo interpretar la fecha: {repr(val)}")


def _fetch_calendar_bytes() -> bytes:
    if not ICAL_URL:
        raise ValueError("Falta GOOGLE_ICAL_URL en .env")
    resp = requests.get(ICAL_URL, timeout=30)
    resp.raise_for_status()
    return resp.content  # bytes


def get_events_today_from_ics() -> List[Dict[str, Any]]:
    """
    Devuelve eventos de HOY como lista de dicts:
    { 'summary': str, 'start': datetime, 'end': datetime }
    """
    tz = pytz.timezone(TZ_NAME)
    day_start, day_end = _today_window(TZ_NAME)

    raw = _fetch_calendar_bytes()
    cal = ICal.from_ical(raw)  # type: ignore[arg-type]

    events_out: List[Dict[str, Any]] = []
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue

        summary = comp.get("SUMMARY")
        dtstart = comp.get("DTSTART")
        dtend = comp.get("DTEND")

        if not dtstart or not dtend:
            # Algunos feeds usan DURATION en vez de DTEND
            duration = comp.get("DURATION")
            if dtstart and duration:
                start_val = dtstart.dt
                start_dt = _to_local_dt(start_val, tz)
                end_dt = start_dt + duration.dt
            else:
                continue
        else:
            start_val = dtstart.dt
            end_val = dtend.dt
            start_dt = _to_local_dt(start_val, tz)
            end_dt = _to_local_dt(end_val, tz)

        # Intersección con hoy (en zona local)
        if (start_dt < day_end) and (end_dt > day_start):
            events_out.append({
                "summary": str(summary) if summary else "(sin título)",
                "start": max(start_dt, day_start),
                "end": min(end_dt, day_end),
            })

    events_out.sort(key=lambda x: x["start"])
    return events_out


def find_free_slots_from_events(
    events: List[Dict[str, Any]],
    min_minutes: int = STUDY_BLOCK_MIN
) -> List[Tuple[datetime, datetime]]:
    tz = pytz.timezone(TZ_NAME)
    day_start, _ = _today_window(TZ_NAME)
    work_start = day_start.replace(hour=WORKDAY_START, minute=0, second=0, microsecond=0)
    work_end = day_start.replace(hour=WORKDAY_END, minute=0, second=0, microsecond=0)

    # Normaliza y recorta a ventana laboral
    intervals: List[Tuple[datetime, datetime]] = []
    for ev in events:
        s = ev["start"].astimezone(tz)
        e = ev["end"].astimezone(tz)
        s = max(s, work_start)
        e = min(e, work_end)
        if e > s:
            intervals.append((s, e))
    intervals.sort(key=lambda x: x[0])

    # Merge de solapamientos usando tuplas
    merged: List[Tuple[datetime, datetime]] = []
    for s, e in intervals:
        if not merged or s > merged[-1][1]:
            merged.append((s, e))
        else:
            last_s, last_e = merged[-1]
            merged[-1] = (last_s, max(last_e, e))

    # Gaps
    free: List[Tuple[datetime, datetime]] = []
    cursor = work_start
    for s, e in merged:
        if s > cursor:
            gap_min = (s - cursor).total_seconds() / 60.0
            if gap_min >= min_minutes:
                free.append((cursor, s))
        cursor = max(cursor, e)

    if work_end > cursor:
        gap_min = (work_end - cursor).total_seconds() / 60.0
        if gap_min >= min_minutes:
            free.append((cursor, work_end))

    return free


def format_slot(slot: Tuple[datetime, datetime]) -> str:
    s, e = slot
    return f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')}"
