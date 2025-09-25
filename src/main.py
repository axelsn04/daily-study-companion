# src/main.py
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv

from news import fetch_news
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events
from finance import fetch_prices, basic_stats, plot_prices
from report import save_report
from email_send import send_email

load_dotenv()

OUTPUT_HTML = os.getenv("REPORT_OUT_PATH", "data/processed/daily_report.html")
SEND_CHANNEL = (os.getenv("SEND_CHANNEL", "email") or "email").lower()
REPORT_TITLE = os.getenv("REPORT_TITLE", "Daily Study & News Companion")


# -------- helpers --------
def _top_headlines_html(news_items: List[Dict[str, Any]], k: int = 3) -> str:
    if not news_items:
        return "<p><em>Sin titulares hoy.</em></p>"
    lis = []
    for a in news_items[:k]:
        title = (a.get("title") or a.get("headline") or "").strip()
        link = (a.get("link") or a.get("url") or "").strip()
        src = (a.get("source") or "").strip()
        meta = f' <span style="color:#748091">· {src}</span>' if src else ""
        if link:
            lis.append(f'<li><a href="{link}" target="_blank" rel="noreferrer">{title}</a>{meta}</li>')
        else:
            lis.append(f"<li>{title}{meta}</li>")
    return "<ul>" + "\n".join(lis) + "</ul>"


def _market_blurbs_html(stats: Dict[str, Dict[str, float]]) -> str:
    if not stats:
        return ""
    # elegir mejor y peor por pct_change
    sortable = []
    for t, st in stats.items():
        try:
            pct = float(st.get("pct_change", 0.0))
            sortable.append((t, pct))
        except Exception:
            continue
    if not sortable:
        return ""
    sortable.sort(key=lambda x: x[1], reverse=True)
    best = sortable[0]
    worst = sortable[-1]
    b_t, b_p = best
    w_t, w_p = worst
    sign = lambda x: ("+" if x >= 0 else "")
    return (
        '<p style="margin:6px 0 0;color:#748091">'
        f"Mercados: mejor {b_t} {sign(b_p)}{b_p:.2f}% · peor {w_t} {sign(w_p)}{w_p:.2f}%"
        "</p>"
    )


def _agent_intro(news_items: List[Dict[str, Any]], stats: Dict[str, Dict[str, float]]) -> Optional[str]:
    """
    Si existe agent.ai_decision, lo usamos para un resumen corto (<80 palabras).
    Si falla o no existe, devolvemos None y dejamos el fallback básico.
    """
    try:
        from agent import ai_decision  # opcional
    except Exception:
        return None

    try:
        # Pasamos solo lo necesario (títulos y fuentes) para prompt compacto
        compact_news = [
            {
                "title": (n.get("title") or n.get("headline") or "")[:200],
                "source": (n.get("source") or ""),
            }
            for n in news_items[:8]
        ]
        compact_stats = {
            t: {"pct_change": float(s.get("pct_change", 0.0))}
            for t, s in list(stats.items())[:8]
            if isinstance(s, dict)
        }
        text = ai_decision(compact_news, compact_stats)  # retorna str breve
        if not text:
            return None
        # Sanitiza y envuelve en HTML simple
        text = text.strip().replace("\n", " ")
        return f'<p style="margin:0 0 6px">{text}</p>'
    except Exception:
        return None


def _build_intro_html(news_items: List[Dict[str, Any]], stats: Dict[str, Dict[str, float]]) -> str:
    # 1) intenta con el agente
    ai_html = _agent_intro(news_items, stats)
    # 2) titulares top + métricas
    headlines_html = _top_headlines_html(news_items, k=3)
    markets_html = _market_blurbs_html(stats)
    # 3) compón
    parts = []
    if ai_html:
        parts.append(ai_html)
    parts.append("<h3 style='margin:8px 0 4px'>Top headlines</h3>")
    parts.append(headlines_html)
    if markets_html:
        parts.append(markets_html)
    return "\n".join(parts)


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

    # 5) Email (subject con fecha local + intro_html). En tu .env ya tienes EMAIL_EMBED_MODE=linkonly
    if SEND_CHANNEL == "email":
        try:
            now_local = datetime.now().astimezone()
            subject = f"{REPORT_TITLE} — {now_local:%Y-%m-%d %H:%M}"
            intro_html = _build_intro_html(news_items, stats)

            # En 'linkonly' no pasamos adjuntos
            send_email(
                subject=subject,
                html_path=out_path,
                attachments=[],
                intro_html=intro_html,
            )
        except Exception as e:
            print(f"[email] Error enviando correo: {e}")


if __name__ == "__main__":
    main()
