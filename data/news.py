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

import os
import json
import urllib.request

def score_headline_relevance(headline: str, question: str) -> float:
    """
    Uses Gemini to score how much a headline increases or decreases
    the probability of a market question resolving YES.
    Returns a likelihood ratio: >1 increases prob, <1 decreases prob.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return 1.0

    prompt = f"""You are a prediction market analyst.

Headline: "{headline}"
Market question: "{question}"

On a scale from -1.0 to +1.0, how much does this headline change the probability
of the market question resolving YES?
-1.0 = strongly decreases probability
 0.0 = no effect
+1.0 = strongly increases probability

Respond with only a single float number, nothing else."""

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0}
    }).encode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={api_key}"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            score = float(text)
            score = max(-1.0, min(1.0, score))
            # convert -1 to +1 into likelihood ratio
            # +1 → LR 3.0, 0 → LR 1.0, -1 → LR 0.33
            return round(3.0 ** score, 4)
    except Exception:
        return 1.0
