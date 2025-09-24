import os
import time
from urllib.parse import quote_plus
from typing import List, Dict
import feedparser
from dotenv import load_dotenv

load_dotenv()

TOPICS = [t.strip() for t in os.getenv("NEWS_TOPICS", "AI,Machine Learning,Fintech,Mexico,Business").split(",") if t.strip()]
MAX_AGE_HOURS = int(os.getenv("NEWS_MAX_AGE_HOURS", "36"))

def _google_news_rss_url(query: str, lang: str = "en-US", region: str = "US") -> str:
    q = quote_plus(query)
    # Google News RSS de búsqueda
    return f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={region}&ceid={region}:{lang}"

def fetch_news(topics: List[str] = TOPICS, limit_per_topic: int = 5) -> List[Dict]:
    """
    Devuelve una lista de artículos: {title, link, published, source, topic}
    """
    now = time.time()
    out: List[Dict] = []
    seen = set()

    for topic in topics:
        url = _google_news_rss_url(topic)
        d = feedparser.parse(url)
        count = 0
        for e in d.entries:
            # Publicación (timestamp si existe)
            published_ts = None
            if hasattr(e, "published_parsed") and e.published_parsed:
                published_ts = time.mktime(e.published_parsed)
                age_h = (now - published_ts) / 3600.0
                if age_h > MAX_AGE_HOURS:
                    continue

            title = getattr(e, "title", "").strip()
            link = getattr(e, "link", "").strip()
            source = getattr(getattr(e, "source", {}), "title", "") or getattr(e, "source", "")
            key = (title, link)
            if not title or not link or key in seen:
                continue

            out.append({
                "title": title,
                "link": link,
                "published": getattr(e, "published", ""),
                "topic": topic,
                "source": source if isinstance(source, str) else str(source),
            })
            seen.add(key)
            count += 1
            if count >= limit_per_topic:
                break

    return out
