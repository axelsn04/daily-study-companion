# src/news.py
from __future__ import annotations

import os
import re
import time
from time import struct_time
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests
import feedparser
import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = os.getenv("NEWS_CONFIG_PATH", "config/news.yml")

# ---------------- Config (YAML + defaults) ----------------

def _load_config() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "news": {
            "limit": 6,
            "max_age_hours": 36,
            "lang": "en-US",
            "region": "US",
            # Patrones (regex) por tópico: edítalos en config/news.yml
            "topics": {
                "AI": [
                    r"\bai\b",
                    r"artificial intelligence",
                    r"gen(ai|erative ai)",
                    r"\bllm(s)?\b",
                    r"gpt(-\d+)?",
                    r"anthropic|openai|deepmind",
                ],
                "Machine Learning": [
                    r"machine[- ]learning",
                    r"\bml\b",
                    r"deep[- ]learning",
                    r"neural (net|network|networks)",
                    r"transformer(s)?",
                    r"\b(model|models|training|fine[- ]tune|fine[- ]tuning)\b",
                ],
                "Fintech": [
                    r"\bfintech\b",
                    r"payment(s)?|paytech",
                    r"bank(ing)?|neobank|digital bank",
                    r"lending|credit|remittance(s)?",
                    r"stripe|visa|mastercard|paypal|square|block( inc)?",
                    r"\bsaas\b",
                ],
            },
            # Dominios permitidos / bloqueados
            "domain_whitelist": [
                "wsj.com", "feeds.a.dj.com",             # WSJ
                "bloomberg.com", "feeds.bloomberg.com",  # Bloomberg
                "ft.com",                                # Financial Times
                "techcrunch.com",
                "theverge.com",
                "semianalysis.com",
                "reuters.com",
                "nytimes.com", "rss.nytimes.com",
                "forbes.com",
                "finance.yahoo.com",
            ],
            "domain_blacklist": [],
        }
    }

    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            if "news" in user_cfg and isinstance(user_cfg["news"], dict):
                # Merge superficial (claves de primer nivel)
                for k, v in user_cfg["news"].items():
                    defaults["news"][k] = v
    except Exception:
        # Si el YAML falla, seguimos con defaults
        pass

    return defaults

CFG = _load_config()
TOPIC_PATTERNS: Dict[str, List[str]] = CFG["news"].get("topics", {})
LIMIT_PER_TOPIC: int = int(CFG["news"].get("limit", 6))
MAX_AGE_HOURS: int = int(CFG["news"].get("max_age_hours", 36))
WL: List[str] = [d.lower() for d in CFG["news"].get("domain_whitelist", [])]
BL: List[str] = [d.lower() for d in CFG["news"].get("domain_blacklist", [])]

# ---------------- RSS sources (curados) ----------------
# Solo medios globales de negocio/tech/AI
RSS_SOURCES: List[Tuple[str, str]] = [
    # WSJ
    ("wsj.com", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("wsj.com", "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml"),
    # Bloomberg
    ("bloomberg.com", "https://feeds.bloomberg.com/markets/news.rss"),
    ("bloomberg.com", "https://feeds.bloomberg.com/technology/news.rss"),
    # Financial Times
    ("ft.com", "https://www.ft.com/technology?format=rss"),
    ("ft.com", "https://www.ft.com/companies/financials?format=rss"),
    # Tech / AI
    ("techcrunch.com", "https://techcrunch.com/feed/"),
    ("theverge.com", "https://www.theverge.com/rss/index.xml"),
    ("semianalysis.com", "https://www.semianalysis.com/feed"),
    # Reuters
    ("reuters.com", "https://www.reuters.com/finance/markets/rss"),
    ("reuters.com", "https://www.reuters.com/technology/rss"),
    # NYTimes
    ("nytimes.com", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
    ("nytimes.com", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    # Forbes
    ("forbes.com", "https://www.forbes.com/innovation/feed/"),
    ("forbes.com", "https://www.forbes.com/money/feed/"),
    # Yahoo Finance
    ("finance.yahoo.com", "https://finance.yahoo.com/news/rssindex"),
]

# Filtrar por whitelist/blacklist si están definidas
RSS_SOURCES = [
    (dom, url)
    for dom, url in RSS_SOURCES
    if (not WL or any(w in dom or w in url for w in WL))
    and (not BL or not any(b in dom or b in url for b in BL))
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept": "application/rss+xml,text/xml,*/*",
}

# ---------------- Utilidades ----------------

def _host(link: str) -> str:
    try:
        return urlparse(link).netloc.lower()
    except Exception:
        return ""

def _fetch_feed(url: str) -> feedparser.FeedParserDict:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return feedparser.parse(r.content)

def _classify_topic(text: str) -> str:
    """
    Clasifica por la primera coincidencia de regex en TOPIC_PATTERNS.
    Si no hay match -> 'General'.
    """
    for topic, patterns in TOPIC_PATTERNS.items():
        if not patterns:
            continue
        for pat in patterns:
            try:
                if re.search(pat, text, flags=re.IGNORECASE):
                    return topic
            except re.error:
                # Si hay un patrón mal escrito en YAML, lo ignoramos
                continue
    return "General"

def _normalize_entry(e: Any, now_ts: float) -> Dict[str, Any] | None:
    title = (getattr(e, "title", "") or "").strip()
    link = (getattr(e, "link", "") or "").strip()
    if not title or not link:
        return None

    host = _host(link)
    if WL and not any(w in host for w in WL):
        return None
    if BL and any(b in host for b in BL):
        return None

    # Fecha (si viene parseada, aplicamos filtro de antigüedad)
    published_str = getattr(e, "published", "") or getattr(e, "updated", "")
    parsed = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
    if isinstance(parsed, struct_time):
        age_h = (now_ts - time.mktime(parsed)) / 3600.0
        if age_h > MAX_AGE_HOURS:
            return None
        published_str = time.strftime("%Y-%m-%d %H:%M", parsed)

    # Fuente
    source_obj = getattr(e, "source", None)
    source = ""
    if source_obj:
        source = getattr(source_obj, "title", "") or str(source_obj)
    else:
        source = getattr(e, "publisher", "") or getattr(e, "author", "") or host

    # Tópico por patrones en título + resumen
    summary = (getattr(e, "summary", "") or "")
    topic = _classify_topic(f"{title}\n{summary}")

    return {
        "title": title,
        "link": link,
        "published": published_str,
        "topic": topic,
        "source": source,
    }

# ---------------- API ----------------

def fetch_news(topics: List[str] | None = None, limit_per_topic: int | None = None) -> List[Dict]:
    """
    Agrega noticias de RSS curados, filtra por dominios y antigüedad (si parseable),
    y clasifica por tópico mediante regex (AI / Machine Learning / Fintech / General).
    Retorna lista de dicts: {title, link, published, source, topic}
    """
    per_topic_limit = LIMIT_PER_TOPIC if limit_per_topic is None else int(limit_per_topic)
    now_ts = time.time()
    out: List[Dict] = []
    seen = set()
    per_topic_count: Dict[str, int] = {}

    for _, url in RSS_SOURCES:
        try:
            d = _fetch_feed(url)
        except Exception:
            continue

        for e in d.entries:
            item = _normalize_entry(e, now_ts)
            if not item:
                continue

            topic = item["topic"]
            per_topic_count.setdefault(topic, 0)
            if per_topic_count[topic] >= per_topic_limit:
                continue

            key = (item["title"], item["link"])
            if key in seen:
                continue

            out.append(item)
            seen.add(key)
            per_topic_count[topic] += 1

    return out
