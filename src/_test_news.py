# src/_test_news.py
import os, sys
sys.path.append(os.path.dirname(__file__))  # añade ./src al PYTHONPATH dinámicamente

from news import fetch_news

arts = fetch_news()
print(f"Total artículos: {len(arts)}")
for a in arts[:10]:
    print(f"- [{a.get('topic','')}] {a['published']} | {a.get('source','')} | {a['title']}")
print("(mostrando hasta 10)")
