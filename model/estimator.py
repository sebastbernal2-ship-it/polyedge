import os
import json
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
NAVIGATOR_KEY = os.getenv("NAVIGATOR_KEY", "")
NAVIGATOR_BASE = "https://api.ai.it.ufl.edu/v1"
NAVIGATOR_MODEL = "llama-3.3-70b-instruct"

DOMAIN_PRIORS = {
    "ceasefire": 0.35,
    "nuclear": 0.20,
    "strait": 0.08,
    "attack": 0.15,
    "sanctions": 0.55,
    "diplomatic": 0.40,
    "default": 0.30,
}

DOMAIN_KEYWORDS = {
    "ceasefire": ["ceasefire", "truce", "peace deal", "halt", "agreement"],
    "nuclear": ["nuclear", "enrichment", "iaea", "uranium", "bomb", "warhead"],
    "strait": ["strait of hormuz", "hormuz", "tanker", "shipping lane", "blockade"],
    "attack": ["strike", "attack", "bomb", "missile", "airstrike", "retaliation"],
    "sanctions": ["sanctions", "embargo", "oil ban", "export ban", "treasury"],
    "diplomatic": ["diplomacy", "talks", "negotiations", "envoy", "summit"],
}


def classify_domain(question: str) -> str:
    q = question.lower()
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in kws):
            return domain
    return "default"


def fetch_news(query: str, days_back: int = 3) -> list:
    if not NEWSAPI_KEY:
        return []
    from_date = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "relevancy",
        "pageSize": 5,
        "language": "en",
        "apiKey": NEWSAPI_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        print(f"[NewsAPI error] {e}")
        return []


def summarize_articles(articles: list) -> str:
    snippets = []
    for a in articles[:5]:
        title = a.get("title", "")
        desc = a.get("description", "") or ""
        snippets.append(f"- {title}: {desc[:120]}")
    return "\n".join(snippets) if snippets else "No recent news found."


def llm_score(
    question: str,
    news_summary: str,
    domain: str,
    prior: float,
    use_llm: bool = True,
) -> tuple:
    if not use_llm or not NAVIGATOR_KEY:
        return keyword_fallback(question, news_summary, prior)

    system_prompt = (
        "You are a geopolitical prediction market analyst. "
        "Given a yes/no market question, recent news, and a domain base rate, "
        "output a JSON object with keys: probability (float 0-1) and "
        "reasoning (1-2 sentences). Be concise and calibrated."
    )
    example = '{"probability": 0.42, "reasoning": "..."}'
    user_prompt = (
        f"Question: {question}\n"
        f"Domain: {domain} (base rate: {prior:.0%})\n"
        f"Recent news:\n{news_summary}\n\n"
        f"Respond ONLY with valid JSON like: {example}"
    )

    headers = {
        "Authorization": f"Bearer {NAVIGATOR_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NAVIGATOR_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }

    try:
        r = requests.post(
            f"{NAVIGATOR_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=25,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        prob = max(0.01, min(0.99, float(data["probability"])))
        return prob, data.get("reasoning", "LLM scored.")
    except Exception as e:
        print(f"[Navigator error] {e}")
        return keyword_fallback(question, news_summary, prior)


def keyword_fallback(question: str, news_summary: str, prior: float) -> tuple:
    positive = ["agreement", "ceasefire", "deal", "progress", "talks", "confirmed"]
    negative = ["collapsed", "failed", "escalat", "strike", "attack", "war"]
    text = (question + " " + news_summary).lower()
    pos = sum(text.count(w) for w in positive)
    neg = sum(text.count(w) for w in negative)
    delta = (pos - neg) * 0.04
    prob = max(0.01, min(0.99, prior + delta))
    return prob, f"Keyword fallback: +{pos} positive, -{neg} negative (delta={delta:+.2f})"


def estimate_edge(
    question: str,
    market_prob: float,
    end_date=None,
    use_llm: bool = True,
    use_news: bool = True,
) -> dict:
    domain = classify_domain(question)
    prior = DOMAIN_PRIORS[domain]
    news_articles = fetch_news(f"Iran {question[:60]}") if use_news else []
    news_summary = summarize_articles(news_articles)
    our_prob, reasoning = llm_score(question, news_summary, domain, prior, use_llm)
    edge = our_prob - market_prob
    abs_edge = abs(edge)
    if abs_edge >= 0.15:
        signal = "STRONG"
    elif abs_edge >= 0.08:
        signal = "MODERATE"
    elif abs_edge >= 0.04:
        signal = "WEAK"
    else:
        signal = "NONE"
    direction = "BUY YES" if edge > 0 else "BUY NO"
    days_left = None
    if end_date:
        try:
            ed = datetime.date.fromisoformat(str(end_date)[:10])
            days_left = (ed - datetime.date.today()).days
        except Exception:
            pass
    return {
        "question": question,
        "domain": domain,
        "prior": prior,
        "market_prob": market_prob,
        "our_prob": our_prob,
        "edge": edge,
        "signal": signal,
        "direction": direction if signal != "NONE" else "HOLD",
        "reasoning": reasoning,
        "news_summary": news_summary,
        "end_date": end_date,
        "days_left": days_left,
        "use_llm": use_llm,
        "use_news": use_news,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


def auto_update_priors(articles: list, market_priors: dict) -> dict:
    updated = dict(market_priors)
    pos_words = ["deal", "agreement", "progress", "ceasefire"]
    neg_words = ["collapse", "failed", "escalat", "strike"]
    for a in articles:
        text = (
            (a.get("title") or "") + " " + (a.get("description") or "")
        ).lower()
        pos = sum(text.count(w) for w in pos_words)
        neg = sum(text.count(w) for w in neg_words)
        delta = (pos - neg) * 0.01
        for mid in updated:
            updated[mid] = max(0.01, min(0.99, updated[mid] + delta))
    return updated


def explain_updates(articles: list, market_priors: dict) -> dict:
    """
    Returns an audit trail showing how news moved each market's prior.
    Result shape: {market_id: {"label": str, "final_prob": float, "steps": list}}
    """
    pos_words = ["deal", "agreement", "progress", "ceasefire", "talks"]
    neg_words = ["collapse", "failed", "escalat", "strike", "attack"]
    audit = {}
    for mid, base_p in market_priors.items():
        steps = [{"source": "domain prior", "delta": 0.0, "prob": base_p}]
        current = base_p
        for a in articles:
            text = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
            pos = sum(text.count(w) for w in pos_words)
            neg = sum(text.count(w) for w in neg_words)
            delta = (pos - neg) * 0.01
            if delta != 0:
                current = max(0.01, min(0.99, current + delta))
                steps.append({
                    "source": (a.get("title") or "article")[:60],
                    "delta": round(delta, 3),
                    "prob": round(current, 3),
                })
        audit[mid] = {
            "label": str(mid)[:30],
            "final_prob": round(current, 3),
            "steps": steps,
        }
    return audit
