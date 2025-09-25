# src/report.py
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any

import pandas as pd


def _fmt_dt(dt: datetime) -> str:
    try:
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt)


def _fmt_num(x: float, nd: int = 2) -> str:
    try:
        return f"{x:,.{nd}f}"
    except Exception:
        return str(x)


def _file_uri(p: str) -> str:
    if p.startswith(("http://", "https://", "file://")):
        return p
    if p.startswith("/"):
        return "file://" + p
    return p  # relativo


def _group_news_by_topic(news: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for n in news:
        topic = (n.get("topic") or "General").strip()
        out.setdefault(topic, []).append(n)

    for k in out:
        def _key(n):
            p = n.get("published")
            if isinstance(p, datetime):
                return p
            try:
                return datetime.fromisoformat(str(p))
            except Exception:
                return datetime.min
        out[k] = sorted(out[k], key=_key, reverse=True)
    return out


def _agenda_html(events: List[Dict[str, Any]], free_slots: List[Tuple[datetime, datetime]]) -> str:
    if events:
        rows = []
        for e in events:
            s = _fmt_dt(e["start"]).split(" ")[1]
            title = (e.get("summary") or "(sin título)").strip()
            rows.append(f'<div class="badge-row"><span class="badge">{s}</span><span class="evt">{title}</span></div>')
        events_html = ''.join(rows)
    else:
        events_html = '<div class="empty">Sin eventos hoy</div>'

    if free_slots:
        chips = [f'<span class="chip">{s.strftime("%H:%M")}–{e.strftime("%H:%M")}</span>' for s, e in free_slots]
        gaps_html = ''.join(chips)
    else:
        gaps_html = '<div class="empty">Sin huecos de estudio</div>'

    return f"""
    <aside id="sidebar">
      <section class="card sticky">
        <div class="card-head"><h2>📅 Agenda de hoy</h2></div>
        <div class="card-body">
          <h3>Eventos</h3>
          {events_html}
          <h3>Huecos de estudio</h3>
          <div class="chips">{gaps_html}</div>
        </div>
      </section>
    </aside>
    """


def _markets_cards(stats: Dict[str, Dict[str, float]], chart_paths: List[str]) -> str:
    chart_map: Dict[str, str] = {}
    for p in chart_paths:
        base = os.path.basename(p)
        t = base.replace("_close.png", "").upper()
        chart_map[t] = _file_uri(p)

    cards = []
    keys = sorted(set(list(stats.keys()) + list(chart_map.keys())))
    for t in keys:
        st = stats.get(t, {})
        last = st.get("last")
        pct = st.get("pct_change", 0.0)
        cls = "up" if (pct or 0) > 0 else ("down" if (pct or 0) < 0 else "flat")
        mn = st.get("min"); mx = st.get("max"); sd = st.get("std")
        img = chart_map.get(t, "")

        metrics = f"""
          <div class="kv"><span>Last</span><b>{_fmt_num(last) if last is not None else '—'}</b></div>
          <div class="kv"><span>d/d</span><b class="{cls}">{_fmt_num(pct,2)}%</b></div>
          <div class="kv"><span>Mín</span><b>{_fmt_num(mn) if mn is not None else '—'}</b></div>
          <div class="kv"><span>Máx</span><b>{_fmt_num(mx) if mx is not None else '—'}</b></div>
          <div class="kv"><span>σ</span><b>{_fmt_num(sd) if sd is not None else '—'}</b></div>
        """
        img_html = f'<img src="{img}" alt="{t} chart" loading="lazy"/>' if img else '<div class="noimg">Sin gráfica</div>'

        cards.append(f"""
        <div class="mkt-card">
          <div class="mkt-head">
            <div class="ticker">{t}</div>
            <button class="mini pill" onclick="this.closest('.mkt-card').classList.toggle('big')">↕</button>
          </div>
          <div class="mkt-body">
            <div class="metrics-row">{metrics}</div>
            <div class="chart">{img_html}</div>
          </div>
        </div>
        """)

    return "".join(cards)


def _markets_html(stats: Dict[str, Dict[str, float]], chart_paths: List[str]) -> str:
    return f"""
    <section id="markets" class="card" data-carousel="markets">
      <div class="card-head">
        <h2>💹 Markets</h2>
        <div class="nav">
          <button class="navbtn prev" aria-label="Anterior">←</button>
          <button class="navbtn next" aria-label="Siguiente">→</button>
        </div>
      </div>
      <div class="card-body">
        <div class="carousel-wrap">
          <div class="viewport">
            <div class="track">
              {_markets_cards(stats, chart_paths)}
            </div>
          </div>
        </div>
      </div>
    </section>
    """


def _news_html(news: List[Dict[str, Any]]) -> str:
    groups = _group_news_by_topic(news)
    topics = sorted(groups.keys(), key=lambda x: (x.lower() != "ai", x))

    filters = ''.join(f'<button class="pill" data-topic="{t}">{t}</button>' for t in topics)

    blocks = []
    for t in topics:
        lis = []
        for a in groups[t]:
            title = (a.get("title") or "").strip()
            link = (a.get("link") or a.get("url") or "").strip()
            src = (a.get("source") or "").strip()
            pub = a.get("published")
            pub_str = pub.strftime("%Y-%m-%d %H:%M") if isinstance(pub, datetime) else str(pub or "")
            lis.append(f"""
              <li class="news-item" data-topic="{t}">
                <span class="dot"></span>
                <a href="{link}" target="_blank" rel="noreferrer">{title}</a>
                <div class="meta">{pub_str}{' · ' if pub_str and src else ''}<span class="src">{src}</span></div>
              </li>
            """)
        blocks.append(f"""
          <div class="news-group" data-group="{t}">
            <div class="topic-chip">{t}</div>
            <ul class="news-list">{''.join(lis)}</ul>
          </div>
        """)

    content = ''.join(blocks) if blocks else '<div class="empty">Sin artículos recientes.</div>'

    return f"""
    <section id="news" class="card">
      <div class="card-head">
        <h2>📰 Noticias</h2>
        <div class="filters">
          <button class="pill" data-topic="all" data-active="true">All</button>
          {filters}
        </div>
      </div>
      <div class="card-body">{content}</div>
    </section>
    """


def save_report(
    out_path: str,
    news: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    free_slots: List[Tuple[datetime, datetime]],
    prices: Dict[str, pd.DataFrame],  # no se usa directamente aquí, pero se mantiene la firma
    stats: Dict[str, Dict[str, float]],
    chart_paths: List[str],
) -> str:
    template_path = Path("templates/report.html")
    if not template_path.exists():
        raise FileNotFoundError("Falta templates/report.html")

    now = datetime.now().astimezone()
    tzname = str = ((now.tzinfo.tzname(now) if now.tzinfo else None) or "Local")

    html = template_path.read_text(encoding="utf-8")
    html = (
        html.replace("__DATE_TIME__", now.strftime("%Y-%m-%d %H:%M"))
            .replace("__TZ__", tzname)
            .replace("__GEN_AT__", now.strftime("%Y-%m-%d %H:%M"))
            .replace("__SIDEBAR__", _agenda_html(events, free_slots))
            .replace("__MARKETS__", _markets_html(stats, chart_paths))
            .replace("__NEWS__", _news_html(news))
    )

    Path(os.path.dirname(out_path)).mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
