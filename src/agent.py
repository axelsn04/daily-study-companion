# src/agent.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Dict, List

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

def _pick_headlines(news: List[Dict[str, Any]], k: int = 5) -> List[str]:
    # Ordena por fecha si la tuviéramos; si no, toma primeras
    items = []
    for n in news:
        title = (n.get("title") or "").strip()
        if not title:
            continue
        pub = n.get("published")
        items.append((pub, title))
    # más recientes primero si hay fecha
    items.sort(key=lambda t: (str(t[0]) or ""), reverse=True)
    titles = [t for _, t in items][:k]
    # si no hay fechas, igual titles ya tiene primeras K
    if not titles and news:
        titles = [(n.get("title") or "").strip() for n in news[:k] if n.get("title")]
    return [t for t in titles if t]

def _mk_markets_blurb(stats: Dict[str, Dict[str, float]]) -> str:
    if not stats:
        return ""
    parts = []
    for tk in ("NVDA","MSFT","AMZN","TSLA","SPY","^GSPC"):
        s = stats.get(tk) or stats.get(tk.replace("^GSPC","SPY"))
        if not s: 
            continue
        pct = s.get("pct_change")
        if pct is None:
            continue
        parts.append(f"{tk} {pct:+.2f}%")
    return " | ".join(parts)

def _heuristic_digest(news: List[Dict[str, Any]], stats: Dict[str, Dict[str, float]], k: int = 5) -> str:
    titles = _pick_headlines(news, k=k)
    markets = _mk_markets_blurb(stats)
    lines = []
    if titles:
        lines.append("<ul>" + "".join(f"<li>{t}</li>" for t in titles) + "</ul>")
    if markets:
        lines.append(f"<p><strong>Markets:</strong> {markets}</p>")
    if not lines:
        lines.append("<p>No headlines today.</p>")
    return "\n".join(lines)

def _openai_digest(news: List[Dict[str, Any]], stats: Dict[str, Dict[str, float]], k: int = 5) -> str:
    try:
        from openai import OpenAI  # pip install openai
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return _heuristic_digest(news, stats, k=k)

    titles = _pick_headlines(news, k=k)
    markets = _mk_markets_blurb(stats)

    prompt = (
        "You are a concise assistant. Create a compact HTML snippet for an email body with:\n"
        f"- Top {len(titles)} headlines as bullet points (short, no fluff)\n"
        "- One line with key market moves if provided.\n"
        "Keep it simple HTML (ul/li, p, strong). No CSS.\n\n"
        f"Headlines:\n" + "\n".join(f"- {t}" for t in titles) + "\n\n"
        f"Markets: {markets or '(none)'}\n"
    )
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
        )
        text = resp.choices[0].message.content.strip()
        # Por si el modelo respondió con texto plano, envolvemos mínimamente
        if "<ul" not in text and "<p" not in text:
            text = "<ul>" + "".join(f"<li>{t}</li>" for t in titles) + "</ul>" + (
                f"<p><strong>Markets:</strong> {markets}</p>" if markets else ""
            )
        return text
    except Exception:
        return _heuristic_digest(news, stats, k=k)

def generate_digest_html(news: List[Dict[str, Any]], stats: Dict[str, Dict[str, float]], k: int = 5) -> str:
    """Devuelve HTML breve para el correo (link-only)."""
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    header = f"<h3>Daily Agent Digest — {today}</h3>"
    body = _openai_digest(news, stats, k=k) if OPENAI_API_KEY else _heuristic_digest(news, stats, k=k)
    return header + "\n" + body
