# src/run_agent.py
from __future__ import annotations
import argparse
import os
from datetime import datetime

from dotenv import load_dotenv

from news import fetch_news
from finance import fetch_prices, basic_stats
from agent import generate_digest_html, ai_decision

load_dotenv()


def _markets_line(stats: dict) -> str:
    order = ("NVDA", "MSFT", "AMZN", "TSLA", "SPY", "^GSPC")
    parts = []
    for tk in order:
        s = stats.get(tk) or (stats.get("SPY") if tk == "^GSPC" else None)
        if not s:
            continue
        pct = s.get("pct_change")
        if pct is None:
            continue
        parts.append(f"{tk} {pct:+.2f}%")
    return " | ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["digest", "decision"], default="digest",
                    help="digest = genera HTML de resumen; decision = prompt libre al modelo")
    ap.add_argument("--k", type=int, default=5, help="Top K titulares para el digest")
    ap.add_argument("--dry-run", action="store_true", help="Solo imprimir en consola")
    args = ap.parse_args()

    # 1) Datos base
    news_items = fetch_news()
    prices = fetch_prices()
    stats = basic_stats(prices)

    if args.mode == "digest":
        # 2) Digest HTML (para cuerpo de correo)
        html = generate_digest_html(news_items, stats, k=args.k)
        if args.dry_run:
            print(html)
        else:
            # Aquí podrías enviarlo por correo si quisieras
            print(html)
        return

    # ---- MODO decision (prompt libre al modelo) ----
    # Construimos prompts de texto (strings) a partir de news/stats
    today = datetime.now().strftime("%Y-%m-%d")
    system_prompt = (
        "You are a helpful research assistant. Be concise and factual. "
        "If asked to summarize, write short bullet points."
    )

    # Tomamos títulos (hasta k) y añadimos línea de mercados
    titles = []
    for n in news_items[: args.k]:
        t = (n.get("title") or "").strip()
        if t:
            titles.append(f"- {t}")
    markets = _markets_line(stats)

    user_prompt = (
        f"Date: {today}\n"
        f"Top headlines:\n" + "\n".join(titles) + "\n\n"
        f"Markets: {markets or '(none)'}\n\n"
        "Task: Give me a 3-bullet summary. Keep total under ~80 words."
    )

    out = ai_decision(system_prompt, user_prompt)
    if args.dry_run:
        print(out)
    else:
        print(out)


if __name__ == "__main__":
    main()
