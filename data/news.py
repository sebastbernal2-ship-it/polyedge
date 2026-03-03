import os
from newsapi import NewsApiClient
from config import DOMAINS

def get_latest_headlines():
    """Pull today's headlines for each domain keyword."""
    client = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))
    articles = []
    for keyword in DOMAINS:
        resp = client.get_everything(
            q=keyword,
            language="en",
            sort_by="publishedAt",
            page_size=5
        )
        for a in resp.get("articles", []):
            articles.append({
                "keyword":     keyword,
                "title":       a["title"],
                "description": a["description"],
                "published":   a["publishedAt"],
                "url":         a["url"],
                "source":      a["source"]["name"]
            })
    return articles
