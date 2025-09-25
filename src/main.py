# src/main.py
from __future__ import annotations

import os
from datetime import datetime
from dotenv import load_dotenv

from news import fetch_news
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events
from finance import fetch_prices, basic_stats, plot_prices
from report import save_report

# nuevo: email
from email_send import send_email  

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
    prices = fetch_prices()                      # Dict[str, pd.DataFrame]
    stats = basic_stats(prices)                  # Dict[str, Dict[str, float]]
    chart_paths = plot_prices(prices) or []      # List[str] con rutas de imágenes

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

    # 5) Envío por email (si está habilitado)

    if SEND_CHANNEL == "email":
        try:
            from datetime import datetime
            now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

            # Make chart paths absolute (they are relative to the report's directory)
            report_dir = os.path.dirname(out_path)
            abs_attachments = [
                (p if os.path.isabs(p) else os.path.join(report_dir, p))
                for p in (chart_paths or [])
            ]

            send_email(
                subject=f"Daily Study & News — {now}",
                html_path=out_path,             # email_send will also attach this automatically
                attachments=abs_attachments,    # now real filepaths
            )
        except Exception as e:
            print(f"[email] Error enviando correo: {e}")



if __name__ == "__main__":
    main()
