# src/run_agent.py
from __future__ import annotations
import os
import argparse
from datetime import datetime
from typing import Dict, Any, List, Tuple

from dotenv import load_dotenv
load_dotenv()

# Dependencias del proyecto
from news import fetch_news
from finance import fetch_prices, basic_stats
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events
from email_send import send_email

# -------- Config --------
REPORT_PUBLIC_URL = (os.getenv("REPORT_PUBLIC_URL", "") or "").strip()
REPORT_OUT_PATH   = os.getenv("REPORT_OUT_PATH", "docs/daily_report.html")
STUDY_ICS_PATH    = os.getenv("STUDY_ICS_PATH", "docs/study_blocks.ics")
EMAIL_SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[Daily Companion]")

# Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()

# -------- Helpers --------
def _fmt_dt_ics(dt: datetime) -> str:
    """UTC -> YYYYMMDDTHHMMSSZ"""
    from datetime import timezone
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _write_study_ics(free_slots: List[Tuple[datetime, datetime]], path: str) -> str:
    """Crea un ICS con los huecos de estudio en UTC."""
    import uuid
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//DailyStudyCompanion//EN"]
    for s, e in free_slots:
        uid = str(uuid.uuid4())
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_fmt_dt_ics(datetime.now())}",
            f"DTSTART:{_fmt_dt_ics(s)}",
            f"DTEND:{_fmt_dt_ics(e)}",
            "SUMMARY:Study block",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path

def _markets_blurb(stats: Dict[str, Dict[str, float]]) -> str:
    order = ("NVDA","MSFT","AMZN","TSLA","SPY","^GSPC")
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

def _dedup_titles(news: List[Dict[str, Any]], k: int = 8) -> List[str]:
    seen = set()
    out: List[str] = []
    for n in news:
        t = (n.get("title") or "").strip()
        if not t: 
            continue
        key = t.lower()
        if key in seen: 
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= k:
            break
    return out

def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # quita bloque ```...```
        if "```" in t[3:]:
            t = t[3:]
            t = t.split("```", 1)[0]
    return t.strip()

def _ollama_digest(headlines: List[str], markets_line: str) -> str:
    """
    Llama a Ollama (servidor local) para crear un digest más profundo:
    - 3–5 bullets con insight y vínculos entre noticias
    - 2 recomendaciones accionables
    - 1-2 líneas de “Why it matters”
    Devuelve HTML mínimo.
    """
    import requests
    sys_prompt = (
        "You are a financial research aide. Produce a concise HTML snippet for an email. "
        "Use <ul><li> for bullets and short <p> lines. No CSS. "
        "Required sections:\n"
        "1) <h4>Top takeaways</h4> with 3–5 bullet points that synthesize *insights* across headlines.\n"
        "2) <h4>Actions</h4> with exactly 2 concrete suggestions (what to read/track/decide).\n"
        "3) If markets provided, a one-line <p><strong>Markets:</strong> ...</p>.\n"
        "Keep it crisp; avoid fluff; avoid repeating the same link line."
    )
    user_prompt = (
        "Headlines:\n- " + "\n- ".join(headlines) + "\n\n"
        f"Markets: {markets_line or '(none)'}\n"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role":"system","content": sys_prompt},
            {"role":"user","content": user_prompt}
        ],
        "stream": False,
        "options": {"temperature": 0.2}
    }
    r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
    r.raise_for_status()
    content = r.json()["message"]["content"]
    return _strip_code_fences(content)

def _heuristic_digest(headlines: List[str], markets_line: str) -> str:
    bullets = "".join(f"<li>{h}</li>" for h in headlines[:5]) or "<li>No headlines today.</li>"
    body = f"<ul>{bullets}</ul>"
    if markets_line:
        body += f'<p><strong>Markets:</strong> {markets_line}</p>'
    return body

def build_digest_html(news: List[Dict[str, Any]], stats: Dict[str, Dict[str, float]], url_report: str, url_ics: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    headlines = _dedup_titles(news, k=8)
    markets_line = _markets_blurb(stats)

    # Primero intentamos Ollama; si falla, heurístico.
    try:
        digest_core = _ollama_digest(headlines, markets_line)
    except Exception:
        digest_core = _heuristic_digest(headlines, markets_line)

    parts = [f"<h3>Daily Agent Digest — {today}</h3>", digest_core]
    if url_report:
        parts.append(f'<p>Ver reporte completo: <a href="{url_report}">{url_report}</a></p>')
    if url_ics:
        parts.append(f'<p>Suscríbete a tus bloques de estudio: <a href="{url_ics}">{url_ics}</a></p>')
    return "\n".join(parts)

# -------- CLI --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Imprime el digest en consola (no envía correo).")
    args = ap.parse_args()

    # 1) Datos
    news_items = fetch_news()
    prices = fetch_prices()
    stats = basic_stats(prices)

    # 2) Agenda y huecos -> ics
    events = get_events_today_from_ics()
    free_slots = find_free_slots_from_events(events)
    ics_path = _write_study_ics(free_slots, STUDY_ICS_PATH)

    # 3) Digest HTML
    public_ics_url = None
    if REPORT_PUBLIC_URL:
        # Asumiendo GitHub Pages en /docs:
        # daily_report.html -> study_blocks.ics en la misma carpeta pública
        public_ics_url = REPORT_PUBLIC_URL.rsplit("/", 1)[0] + "/study_blocks.ics"

    digest_html = build_digest_html(news_items, stats, REPORT_PUBLIC_URL, public_ics_url or "")

    if args.dry_run:
        print(digest_html)
        return

    # 4) Enviar correo (linkonly, SOLO el digest como body)
    subject = f"Daily Agent Digest {datetime.now().strftime('%Y-%m-%d')}"
    send_email(
        subject=subject,
        html_path=REPORT_OUT_PATH,
        attachments=[],            # en linkonly no adjuntamos
        extra_html=digest_html,    # cuerpo = solo digest (ya no duplica link)
    )
    print("[agent] Email enviado.")


if __name__ == "__main__":
    main()
