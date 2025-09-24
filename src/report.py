import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
from pathlib import Path

from dotenv import load_dotenv
from finance import fetch_prices, basic_stats, plot_prices
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events, format_slot
from news import fetch_news

load_dotenv()

REPORT_TITLE = os.getenv("REPORT_TITLE", "Daily Study & News Companion")
TZ = os.getenv("TZ", "America/Mexico_City")

FIG_DIR = Path("data/processed/figs")
FIG_DIR.mkdir(parents=True, exist_ok=True)

def _finance_section() -> Tuple[str, List[str]]:
    data = fetch_prices()
    imgs: List[str] = []
    rows: List[str] = []
    for t, df in data.items():
        stats = basic_stats(df)
        img_path = FIG_DIR / f"{t.replace('^','IDX_')}.png"
        plot_prices(df, t, save_path=str(img_path))
        imgs.append(str(img_path))

        rows.append(
            f"<tr><td><b>{t}</b></td>"
            f"<td style='text-align:right'>{stats['last']:.2f}</td>"
            f"<td style='text-align:right'>{stats['pct_change']:.2f}%</td>"
            f"<td style='text-align:right'>{stats['min']:.2f}</td>"
            f"<td style='text-align:right'>{stats['max']:.2f}</td>"
            f"<td style='text-align:right'>{stats['std']:.2f}</td></tr>"
        )

    table = (
        "<h2>Mercados</h2>"
        "<table style='border-collapse:collapse;width:100%'>"
        "<thead><tr>"
        "<th style='text-align:left;border-bottom:1px solid #ccc;padding:6px'>Ticker</th>"
        "<th style='text-align:right;border-bottom:1px solid #ccc;padding:6px'>Último</th>"
        "<th style='text-align:right;border-bottom:1px solid #ccc;padding:6px'>Δ%</th>"
        "<th style='text-align:right;border-bottom:1px solid #ccc;padding:6px'>Mín</th>"
        "<th style='text-align:right;border-bottom:1px solid #ccc;padding:6px'>Máx</th>"
        "<th style='text-align:right;border-bottom:1px solid #ccc;padding:6px'>σ</th>"
        "</tr></thead><tbody>"
        + "".join(rows) +
        "</tbody></table>"
    )

    charts = "".join([
    f"<div style='margin:12px 0'><img src='{Path(p).resolve().as_uri()}' style='max-width:100%'/></div>"for p in imgs])
    return table + charts, imgs

def _calendar_section() -> str:
    events = get_events_today_from_ics()
    slots = find_free_slots_from_events(events)

    ev_lines = "".join([f"<li>{e['start'].strftime('%H:%M')}–{e['end'].strftime('%H:%M')} — {e['summary']}</li>" for e in events])
    ev_html = f"<ul>{ev_lines}</ul>" if ev_lines else "<p>(Sin eventos hoy)</p>"

    slot_lines = "".join([f"<li>{format_slot(s)}</li>" for s in slots])
    slot_html = f"<ul>{slot_lines}</ul>" if slot_lines else "<p>(Sin huecos ≥ bloque mínimo)</p>"

    return (
        "<h2>Agenda de hoy</h2>"
        "<h3>Eventos</h3>" + ev_html +
        "<h3>Huecos de estudio</h3>" + slot_html
    )

def _news_section() -> str:
    arts = fetch_news()
    if not arts:
        return "<h2>Noticias</h2><p>(Sin artículos recientes en las horas configuradas)</p>"

    by_topic: Dict[str, List[Dict]] = {}
    for a in arts:
        by_topic.setdefault(a["topic"], []).append(a)

    sections = []
    for topic, items in by_topic.items():
        lis = "".join([f"<li><a href='{i['link']}'>{i['title']}</a> <span style='color:#666'>({i.get('source','')})</span></li>" for i in items])
        sections.append(f"<h3>{topic}</h3><ul>{lis}</ul>")
    return "<h2>Noticias</h2>" + "".join(sections)

def build_report_html() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    header = f"""
    <html><head><meta charset="utf-8"><title>{REPORT_TITLE} — {today}</title></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:#111; line-height:1.45; max-width:900px; margin:24px auto; padding:0 16px">
      <h1 style="margin:0 0 8px">{REPORT_TITLE}</h1>
      <div style="color:#666;margin-bottom:16px">{today} · TZ: {TZ}</div>
      <hr style="border:none;border-top:1px solid #eee;margin:16px 0"/>
    """

    news_html = _news_section()
    cal_html = _calendar_section()
    fin_html, _ = _finance_section()

    footer = """
      <hr style="border:none;border-top:1px solid #eee;margin:16px 0"/>
      <div style="color:#888;font-size:12px">Generado automáticamente.</div>
    </body></html>
    """

    return header + news_html + cal_html + fin_html + footer

def save_report(path: str = "data/processed/daily_report.html") -> str:
    html = build_report_html()
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
