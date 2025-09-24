# src/main.py
from __future__ import annotations

import os
from dotenv import load_dotenv

from news import fetch_news
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events
from finance import fetch_prices, basic_stats, plot_prices
from report import save_report

load_dotenv()

OUTPUT_HTML = os.getenv("REPORT_OUT_PATH", "data/processed/daily_report.html")


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


if __name__ == "__main__":
    main()
