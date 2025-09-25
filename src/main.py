# src/main.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from dotenv import load_dotenv

from news import fetch_news
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events
from finance import fetch_prices, basic_stats, plot_prices
from report import save_report
from email_send import send_email

# Agent digest (headlines + markets)
from agent import generate_digest_html

load_dotenv()

OUTPUT_HTML = os.getenv("REPORT_OUT_PATH", "docs/daily_report.html")
SEND_CHANNEL = os.getenv("SEND_CHANNEL", "email").lower()
REPORT_PUBLIC_URL = (os.getenv("REPORT_PUBLIC_URL", "") or "").strip()
STUDY_ICS_PATH = os.getenv("STUDY_ICS_PATH", "docs/study_blocks.ics")


def _fmt_dt_ics(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_study_ics(free_slots, path: str) -> str | None:
    """Write a minimal ICS with today's free study blocks."""
    if not free_slots:
        return None
    import uuid
    from pathlib import Path

    now = datetime.now(timezone.utc)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DailyStudyCompanion//EN"]
    for s, e in free_slots:
        uid = str(uuid.uuid4())
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_fmt_dt_ics(now)}",
            f"DTSTART:{_fmt_dt_ics(s)}",
            f"DTEND:{_fmt_dt_ics(e)}",
            "SUMMARY:Study block",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    Path(os.path.dirname(path) or ".").mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    # 1) Noticias
    news_items = fetch_news()

    # 2) Agenda (hoy) y huecos de estudio
    events = get_events_today_from_ics()
    free_slots = find_free_slots_from_events(events)

    # 2b) Exportar ICS con bloques de estudio (si hay)
    ics_url = ""
    ics_path = _write_study_ics(free_slots, STUDY_ICS_PATH)
    if ics_path and REPORT_PUBLIC_URL:
        base = REPORT_PUBLIC_URL.rsplit("/", 1)[0]
        ics_url = f"{base}/study_blocks.ics"

    # 3) Mercados
    prices = fetch_prices()
    stats = basic_stats(prices)
    chart_paths = plot_prices(prices) or []

    # 4) Reporte HTML estilizado
    out_path = save_report(
        out_path=OUTPUT_HTML,
        news=news_items,
        events=events,
        free_slots=free_slots,
        prices=prices,
        stats=stats,
        chart_paths=chart_paths,
    )
    print(f"Reporte generado: {out_path}")

    # 5) Email (link-only) con digest + enlaces (reporte + ICS)
    if SEND_CHANNEL == "email":
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            subject = f"Daily Report {today_str}"

            digest_html = generate_digest_html(news_items, stats, k=5)

            extras = []
            if REPORT_PUBLIC_URL:
                extras.append(f'<p>Ver reporte completo: <a href="{REPORT_PUBLIC_URL}">{REPORT_PUBLIC_URL}</a></p>')
            if ics_url:
                extras.append(f'<p>Suscríbete a tus bloques de estudio: <a href="{ics_url}">{ics_url}</a></p>')

            body_html = digest_html + ("\n" + "\n".join(extras) if extras else "")

            send_email(
                subject=subject,
                html_path=out_path,      # en link-only no se adjunta, pero lo mantenemos por consistencia
                attachments=[],
                extra_html=body_html,    # 👈 usar extra_html (soportado por tu email_send.py)
            )
        except Exception as e:
            print(f"[email] Error enviando correo: {e}")


if __name__ == "__main__":
    main()
