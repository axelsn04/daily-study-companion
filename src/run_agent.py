# src/run_agent.py
from __future__ import annotations
import json
from pathlib import Path

from news import fetch_news
from finance import fetch_prices, basic_stats
from agent import ai_decision


def main():
    # 1) Noticias
    news_items = fetch_news()

    # 2) Finanzas
    prices = fetch_prices()
    stats = basic_stats(prices)

    # 3) El agente decide
    digest = ai_decision(news_items, stats)

    # 4) Guardar salida en un txt temporal
    out_file = Path("data/processed/agent_digest.txt")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(digest, encoding="utf-8")

    print(f"[agent] Digest saved: {out_file}")


if __name__ == "__main__":
    main()
