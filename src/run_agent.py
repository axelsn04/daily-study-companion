# src/run_agent.py
from __future__ import annotations

import os
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

from dotenv import load_dotenv
load_dotenv()

from news import fetch_news
from finance import fetch_prices, basic_stats
from calendar_sync import get_events_today_from_ics, find_free_slots_from_events
from email_send import send_email

# --- Config desde .env ---
REPORT_PUBLIC_URL      = (os.getenv("REPORT_PUBLIC_URL", "") or "").strip()
REPORT_OUT_PATH        = os.getenv("REPORT_OUT_PATH", "docs/daily_report.html")
STUDY_ICS_PATH         = os.getenv("STUDY_ICS_PATH", "docs/study_blocks.ics")
EMAIL_SUBJECT_PREFIX   = os.getenv("EMAIL_SUBJECT_PREFIX", "[Daily Companion]")
OLLAMA_MODEL           = (os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct") or "qwen2.5:3b-instruct").strip()
DIGEST_LANG            = (os.getenv("DIGEST_LANG", "es") or "es").lower()  # es / en


# ---------- ICS helpers ----------
def _fmt_dt_ics(dt: datetime) -> str:
    # A ICS UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_study_ics(free_slots: List[Tuple[datetime, datetime]], path: str) -> Optional[str]:
    """
    Escribe un ICS básico con eventos "Study block" para los huecos recibidos.
    Devuelve la ruta escrita o None si no se escribió.
    """
    if not free_slots:
        return None

    import uuid
    from pathlib import Path

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DailyStudyCompanion//EN"]
    now = datetime.now(timezone.utc)

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


# ---------- Digest helpers ----------
def _markets_blurb(stats: Dict[str, Dict[str, float]]) -> str:
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


def _collect_headlines(news: List[Dict[str, Any]], k: int = 5) -> List[Tuple[str, str]]:
    """Devuelve [(source, title)] sin duplicados, hasta k."""
    seen = set()
    out: List[Tuple[str, str]] = []
    for n in news:
        title = (n.get("title") or "").strip()
        if not title:
            continue
        source = (n.get("source") or "").strip() or "News"
        key = (source.lower(), title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((source, title))
        if len(out) >= k:
            break
    return out


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    # elimina ``` o ```html envolventes
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 3:
            t = parts[1]
    return t.strip()


def _ollama_digest(headlines: List[Tuple[str, str]], markets_line: str) -> str:
    """
    Llama a Ollama chat (local) para sintetizar titulares en HTML muy simple.
    """
    import requests

    # Construcción de prompts
    hl_block = "\n".join(f"- [{src}] {ttl}" for src, ttl in headlines) if headlines else "(sin titulares)"
    lang = "Spanish" if DIGEST_LANG.startswith("es") else "English"
    sys_prompt = (
        f"You are a concise financial/tech briefing assistant. Respond in {lang}. "
        "Return ONLY minimal HTML (h4, ul/li, p, strong). No CSS, no code fences.\n\n"
        "Write EXACTLY one section:\n"
        "  <h4>Top takeaways</h4>\n"
        "    • 3–5 bullets synthesized across headlines (not title restatement).\n\n"
        "Rules:\n"
        "- Use ONLY the provided headlines; DO NOT invent facts.\n"
        "- Each bullet ≤ 18 words.\n"
        "- If markets_line is provided, append a final <p><strong>Markets:</strong> ...</p> exactly.\n"
        "- Do NOT include any other sections or links."
    )
    user_prompt = (
        f"Headlines:\n{hl_block}\n\n"
        f"Markets: {markets_line or '(none)'}\n"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user",  "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 4096},
    }

    print(f"[agent] Using Ollama model: {OLLAMA_MODEL}")
    r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
    r.raise_for_status()
    content = r.json()["message"]["content"]
    return _strip_code_fences(content)


def _heuristic_digest(headlines: List[Tuple[str, str]], markets_line: str) -> str:
    # Fallback simple y limpio
    items = "".join(f"<li>{ttl}</li>" for _, ttl in headlines[:5]) or "<li>Sin titulares hoy.</li>"
    body = f"<h4>Top takeaways</h4><ul>{items}</ul>"
    if markets_line:
        body += f'<p><strong>Markets:</strong> {markets_line}</p>'
    return body


def build_digest_html(news: List[Dict[str, Any]],
                      stats: Dict[str, Dict[str, float]],
                      url_report: str,
                      url_ics: Optional[str]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    headlines = _collect_headlines(news, k=5)
    markets_line = _markets_blurb(stats)

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


# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="No envía email; imprime el digest HTML")
    args = ap.parse_args()

    # 1) Datos
    news_items = fetch_news()
    prices = fetch_prices()
    stats = basic_stats(prices)

    events = get_events_today_from_ics()
    free_slots = find_free_slots_from_events(events)

    # 2) ICS (bloques de estudio) — solo si hay huecos
    public_ics_url = None
    ics_path = _write_study_ics(free_slots, STUDY_ICS_PATH) if free_slots else None
    if ics_path and REPORT_PUBLIC_URL:
        # ej: https://.../daily_report.html  ->  https://.../study_blocks.ics
        base = REPORT_PUBLIC_URL.rsplit("/", 1)[0]
        public_ics_url = f"{base}/study_blocks.ics"

    # 3) Digest HTML para el email (cuerpo)
    digest_html = build_digest_html(news_items, stats, REPORT_PUBLIC_URL, public_ics_url)

    if args.dry_run:
        print(digest_html)
        return

    # 4) Envío de email (modo link-only + cuerpo = digest)
    subject = f"{EMAIL_SUBJECT_PREFIX} Daily Agent Digest {datetime.now().strftime('%Y-%m-%d')}"
    send_email(
        subject=subject,
        html_path=REPORT_OUT_PATH,   # en link-only se ignoran adjuntos
        attachments=[],
        extra_html=digest_html,      # cuerpo = SOLO el digest
    )
    print("[agent] Email enviado.")


if __name__ == "__main__":
    main()
