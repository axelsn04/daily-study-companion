# src/agent.py
from __future__ import annotations
import os
import re
from datetime import datetime
from typing import Any, Dict, List

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


def _pick_headlines(news: List[Dict[str, Any]], k: int = 5) -> List[str]:
    items = []
    for n in news:
        title = (n.get("title") or "").strip()
        if not title:
            continue
        pub = n.get("published")
        items.append((pub, title))
    # más recientes primero si hay fecha; si no, mantiene orden de llegada
    try:
        items.sort(key=lambda t: (str(t[0]) or ""), reverse=True)
    except Exception:
        pass
    titles = [t for _, t in items][:k]
    if not titles and news:
        titles = [(n.get("title") or "").strip() for n in news[:k] if n.get("title")]
    return [t for t in titles if t]


def _mk_markets_blurb(stats: Dict[str, Dict[str, float]]) -> str:
    if not stats:
        return ""
    parts = []
    for tk in ("NVDA", "MSFT", "AMZN", "TSLA", "SPY", "^GSPC"):
        s = stats.get(tk) or (stats.get("SPY") if tk == "^GSPC" else None)
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
    blocks = []
    if titles:
        blocks.append("<ul>" + "".join(f"<li>{t}</li>" for t in titles) + "</ul>")
    if markets:
        blocks.append(f"<p><strong>Markets:</strong> {markets}</p>")
    if not blocks:
        blocks.append("<p>No headlines today.</p>")
    return "\n".join(blocks)


# ---------- Limpieza de respuestas del modelo ----------
_CODE_FENCE_RE = re.compile(r"^```[\w-]*\s*$")
_HTML_FIRST_TAG_RE = re.compile(r"<(ul|ol|p|h[1-6]|div|section|article)\b", re.I)

def _strip_code_fences(text: str) -> str:
    # Quita líneas que son ``` o ```html
    lines = [ln for ln in text.splitlines() if not _CODE_FENCE_RE.match(ln.strip())]
    return "\n".join(lines).strip()

def _trim_to_first_html_block(text: str) -> str:
    """
    Recorta cualquier prefacio antes del primer tag HTML 'real'.
    Si no encuentra, devuelve el original.
    """
    m = _HTML_FIRST_TAG_RE.search(text)
    if not m:
        return text.strip()
    return text[m.start():].strip()

def _sanitize_model_html(text: str, fallback_titles: List[str], markets: str) -> str:
    # 1) quitar backticks
    t = _strip_code_fences(text or "")
    # 2) recortar prefacio hasta el primer tag
    t = _trim_to_first_html_block(t)
    # 3) si aún no parece HTML, hacemos fallback mínimo
    if "<" not in t or ">" not in t:
        base = "<ul>" + "".join(f"<li>{h}</li>" for h in fallback_titles) + "</ul>"
        if markets:
            base += f"\n<p><strong>Markets:</strong> {markets}</p>"
        return base
    return t


# ---------- Vía OpenAI (si hay API key), con sanitización ----------
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
        "Return ONLY HTML (ul/li, p, strong). No Markdown fences, no preface.\n\n"
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
        raw = resp.choices[0].message.content.strip()
        return _sanitize_model_html(raw, titles, markets)
    except Exception:
        return _heuristic_digest(news, stats, k=k)


def generate_digest_html(news: List[Dict[str, Any]], stats: Dict[str, Dict[str, float]], k: int = 5) -> str:
    """Devuelve HTML breve para el correo (link-only)."""
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    header = f"<h3>Daily Agent Digest — {today}</h3>"
    body = _openai_digest(news, stats, k=k) if OPENAI_API_KEY else _heuristic_digest(news, stats, k=k)
    return header + "\n" + body


# ---------- Modo “decision” (prompt libre) ----------
def ai_decision(system_prompt: str, user_prompt: str) -> str:
    """
    Devuelve texto (no HTML obligatorio) de una llamada libre al modelo.
    Si no hay OPENAI_API_KEY, devuelve un resumen heurístico mínimo.
    """
    if not OPENAI_API_KEY:
        # Fallback simple: eco recortado
        return (user_prompt or "").strip()[:400]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return (user_prompt or "").strip()[:400]