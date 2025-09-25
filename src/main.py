# src/main.py
from __future__ import annotations

import os
from datetime import datetime
from dotenv import load_dotenv

from news import fetch_news
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events
from finance import fetch_prices, basic_stats, plot_prices
from report import save_report
from email_send import send_email

# 👇 NUEVO: digest del agente para el cuerpo del email
from agent import generate_digest_html

load_dotenv()

OUTPUT_HTML = os.getenv("REPORT_OUT_PATH", "data/processed/daily_report.html")
SEND_CHANNEL = os.getenv("SEND_CHANNEL", "email").lower()


def main() -> None:
    # 1) Noticias
    news_items = fetch_news()

    # 2) Agenda (hoy) y huecos de estudio
    events = get_events_today_from_ics()
    free_slots = find_free_slots_from_events(events)

    # 3) Mercados: precios, estadísticas y gráficas
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

    # 5) Envío por email (link-only) + digest del agente en el cuerpo
    if SEND_CHANNEL == "email":
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            subject = f"Daily Report {today_str}"

            digest_html = generate_digest_html(news_items, stats, k=5)

            # Link-only, sin adjuntos; metemos digest como body_html
            send_email(
                subject=subject,
                html_path=out_path,
                attachments=[],
                body_html=digest_html,
            )
        except Exception as e:
            print(f"[email] Error enviando correo: {e}")


if __name__ == "__main__":
    main()
